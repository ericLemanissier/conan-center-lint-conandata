import logging
import os
import sys

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
        return session.head(url, timeout=timeout)
    except requests.exceptions.Timeout:
        logging.warning("timeout when contacting %s", url)
    except requests.exceptions.ConnectionError:
        logging.warning("connection error when contacting %s", url)
    return None


def check_alternative_archives(url:str, orig_size:int | None):
    # The suffixes are ranked by their typical compression efficiency
    archive_suffixes = [".tar.xz", ".tar.bz2", ".tar.gz", ".tgz", ".zip"]
    for suffix in archive_suffixes:
        if url.endswith(suffix):
            without_suffix = url[: -len(suffix)]
            break
    else:
        # Not an archive
        return
    results = []
    for suffix in archive_suffixes:
        new_url = without_suffix + suffix
        if new_url == url:
            if orig_size is None:
                # Server does not report sizes and only worse formats remain
                return
            # Skip the request for the original URL
            continue
        r = test_url(new_url, timeout=2)
        if r and r.ok:
            if "Content-Length" not in r.headers:
                print(f"a potentially smaller archive exists at {new_url}")
                return
            size = int(r.headers["Content-Length"])
            results.append((size, new_url))
    results = sorted(results)
    if results:
        best_size, best_url = results[0]
        if orig_size and best_size and best_size < orig_size:
            improvement = (orig_size - best_size) / orig_size
            print(f"a {improvement:.1%} smaller archive exists at {best_url}")


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
        if response and response.ok:
            orig_size = response.headers.get("Content-Length")
            check_alternative_archives(url, int(orig_size) if orig_size is not None else None)
        elif response:
            print(f"url {url} is not available ({response.status_code})")
        else:
            print(f"url {url} is not available")

    if at_least_one_version_in_url:
        for vers in versions_not_in_url:
            print(f"url of {vers} does not contain version\n")

    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main("."))
    sys.exit(main(sys.argv[1]))
