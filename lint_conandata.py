import logging
import os
import sys
from urllib.parse import urlparse

import requests
import yaml

session = requests.Session()


def iterate_urls(node):
    for version, version_data in node.items():
        if "sha256" in version_data:
            url = version_data["url"]
            sha = version_data["sha256"]
            if isinstance(url, str):
                yield version, url, sha
            else:
                for url_ in url:
                    yield version, url_, sha


def test_url(url: str, timeout: int = 10) -> requests.Response | None:
    try:
        return session.head(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.Timeout:
        logging.warning("timeout when contacting %s", url)
    except requests.exceptions.ConnectionError as ex:
        logging.warning("connection error when contacting %s: %s", url, ex)
    return None


def _get_content_length(response: requests.Response) -> int | None:
    content_length = response.headers.get("Content-Length")
    if content_length is None or not content_length.isdigit() or content_length == "0":
        return None
    return int(content_length)


def check_alternative_archives(url: str, orig_size: int | None):
    parsed_url = urlparse(url)
    assert parsed_url.hostname is not None, f"Url {url=} does not have a hostname, {parsed_url=}"
    if parsed_url.hostname.endswith("github.com") and "/releases/download/" not in parsed_url.path:
        # Ignore archives generated automatically from tags and hashes, as well as individual files.
        return

    # The suffixes are ranked by their typical compression efficiency
    archive_suffixes = [".tar.xz", ".tar.bz2", ".tar.gz", ".tgz", ".zip"]
    for suffix in archive_suffixes:
        if url.endswith(suffix):
            without_suffix = url[: -len(suffix)]
            break
    else:
        # Not an archive
        return

    results: list[tuple[int | None, str]] = []
    if "/-/archive/" in parsed_url.path:
        # This is most likely a GitLab archive, can limit the check to just .tar.bz2
        archive_suffixes = [".tar.bz2"]
        results.append((orig_size, url))

    for suffix in archive_suffixes:
        new_url = without_suffix + suffix
        if new_url == url:
            size = orig_size
        else:
            response = test_url(new_url, timeout=10)
            if not response or not response.ok:
                continue
            size = _get_content_length(response)
        results.append((size, new_url))
        if size is None:
            break

    if any(size is None for size, _ in results):
        best_size, best_url = results[0]
        if best_url != url:
            print(f"a potentially smaller archive exists at {best_url}\n")
    else:
        best_size, best_url = min(results)
        if best_url != url:
            assert orig_size is not None and best_size is not None, f"orig_size or best_size is None for {url=}, {results=}, {archive_suffixes=}"
            improvement = (orig_size - best_size) / orig_size
            if improvement >= 0.0005 and orig_size - best_size > 1024:
                print(f"a {improvement:.1%} ({(orig_size - best_size)/1024:.0f}kB) smaller archive exists at {best_url}\n")


def main(path: str) -> int:
    if path.endswith("conandata.yml"):
        path = path[0:-13]
    with open(os.path.join(path, "conandata.yml"), encoding="utf-8") as file:
        conandata = yaml.safe_load(file)

    shas: dict[str, str] = {}
    urls: list[str] = []
    versions_not_in_url = []
    at_least_one_version_in_url = False

    for version, url, sha in iterate_urls(conandata["sources"]):
        if sha in shas and shas[sha] != version:
            print(f"sha256 {sha} is present twice for version {version}\n")
        else:
            shas[sha] = version

        if url in urls:
            print(f"url {url} is present twice for version {version}\n")
        else:
            urls.append(url)

        if url.startswith("http://"):
            logging.warning("url %s uses non secure http", url)
        elif not url.startswith("https://"):
            logging.warning("unknown url scheme %s", url)

        version_lower = version.lower()
        url_lower = url.lower()
        if not version_lower.startswith("cci."):
            if (
                (version_lower in url_lower)
                or (version_lower.replace(".", "") in url_lower)
                or (version_lower.replace(".", "_") in url_lower)
                or (version_lower.replace("-", "") in url_lower)
                or (version_lower.endswith(".0") and version_lower[:-2] in url_lower)
            ):
                at_least_one_version_in_url = True
            else:
                versions_not_in_url.append((version, url))

        response = test_url(url)
        if response is None:
            print(f"url {url} is not available\n")
        elif not response.ok:
            print(f"url {url} is not available ({response.status_code})\n")
        else:
            orig_size = _get_content_length(response)
            check_alternative_archives(url, orig_size)

    if at_least_one_version_in_url:
        for vers in versions_not_in_url:
            print(f"url of {vers} does not contain version\n")

    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main("."))
    sys.exit(main(sys.argv[1]))
