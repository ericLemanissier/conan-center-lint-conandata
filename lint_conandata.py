import logging
import os
import sys
from urllib.parse import urlparse

import httpx
import yaml

client = httpx.Client()


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


def test_url(url: str, timeout: int = 10) -> httpx.Response | None:
    try:
        return client.head(url, timeout=timeout, follow_redirects=True)
    except httpx.TimeoutException:
        logging.warning("timeout when contacting %s", url)
    except httpx.ConnectError as ex:
        logging.warning("connection error when contacting %s: %s", url, ex)
    return None


def _get_content_length(response: httpx.Response) -> int | None:
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
            if not response or not response.is_success:
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

def in_allow_list(version: str, url: str) -> bool:
    return {
        "https://blend2d.com/download/blend2d-beta18.zip": "0.0.18",
        "https://blend2d.com/download/blend2d-beta17.zip": "0.0.17",

        "https://heasarc.gsfc.nasa.gov/FTP/software/fitsio/c/cfitsio-3.49.tar.gz": "3.490",
        "https://heasarc.gsfc.nasa.gov/FTP/software/fitsio/c/cfitsio-3.48.tar.gz": "3.480",
        "https://heasarc.gsfc.nasa.gov/FTP/software/fitsio/c/cfitsio-3.47.tar.gz": "3.470",

        "https://github.com/electronicarts/EABase/archive/d1be0a1d0fc01a9bf8f3f2cea75018df0d2410ee.zip": "2.09.12",

        "https://github.com/foonathan/lexy/releases/download/v2022.12.0/lexy-src.zip": "2022.12.00",
        "https://github.com/foonathan/lexy/releases/download/v2022.05.1/lexy-src.zip": "2022.05.01",

        "https://github.com/foonathan/memory/archive/refs/tags/v0.7-3.tar.gz": "0.7.3",
        "https://github.com/foonathan/memory/archive/refs/tags/v0.7-2.tar.gz": "0.7.2",
        "https://github.com/foonathan/memory/archive/refs/tags/v0.7-1.tar.gz": "0.7.1",

        "https://github.com/dnwrnr/sgp4/archive/f5cb54b382a5b4787432ab5b9a1e83de1a224610.tar.gz": "20191207",

        "https://github.com/mackron/miniaudio/archive/a0dc1037f99a643ff5fad7272cd3d6461f2d63fa.tar.gz": "0.11.11",
        "https://github.com/mackron/miniaudio/archive/4dfe7c4c31df46e78d9a1cc0d2d6f1aef5a5d58c.tar.gz": "0.11.9",
        "https://github.com/mackron/miniaudio/archive/82e70f4cbe6e613c8edc0ac7b97ff3dd00f2ca27.tar.gz": "0.11.8",
        "https://github.com/mackron/miniaudio/archive/073b7bbbba3a27adcf44fd62bd055ccee67e1973.tar.gz": "0.11.7",
        "https://github.com/mackron/miniaudio/archive/c3a9ab9b900b1ac316f7e2cb5e05e5cc27179f19.tar.gz": "0.11.6",
        "https://github.com/mackron/miniaudio/archive/42abbbea4602af80d1ccb4a22cdc35813aceee7a.tar.gz": "0.11.2",
        "https://github.com/mackron/miniaudio/archive/37fe1343f04f6fd9bd82229ca50a48b77ecce564.tar.gz": "0.10.40",
        "https://github.com/mackron/miniaudio/archive/8bf157f10e278302f8a6c1c9cd1065f2bea26dd2.tar.gz": "0.10.39",

        "https://github.com/joboccara/NamedType/archive/27cb8d9e0a0d40e786ed43da1388c73f0409fda0.zip": "20190324",

        "https://github.com/Immediate-Mode-UI/Nuklear/archive/74a4df4eb965150ede86fefa6c147476541078a4.zip": "4.06.1",
        "https://github.com/Immediate-Mode-UI/Nuklear/archive/d9ddd1810f8e43911c06f4f86eab3053db757adc.zip": "4.03.1",
        "https://github.com/Immediate-Mode-UI/Nuklear/archive/9f0bca461b028c1f8b638beeba1859045ebe1ac3.zip": "4.02.1",
        "https://github.com/Immediate-Mode-UI/Nuklear/archive/e08d7b418fed2c2971a9b878a4e0340ebc8c4c8a.zip": "4.01.9",
        "https://github.com/Immediate-Mode-UI/Nuklear/archive/82d85e94e19258fb52ea042c7002770aac69bdf8.zip": "4.01.7",
        "https://github.com/Immediate-Mode-UI/Nuklear/archive/bb7c2519a3981de793617eeca975ba8edec29971.zip": "4.01.5",

        "https://github.com/KhronosGroup/OpenCL-CLHPP/archive/refs/tags/v2.0.16.tar.gz": "2022.01.04",
        "https://github.com/KhronosGroup/OpenCL-CLHPP/archive/refs/tags/v2.0.15.tar.gz": "2021.06.30",
        "https://github.com/KhronosGroup/OpenCL-CLHPP/archive/refs/tags/v2.0.14.tar.gz": "2021.04.29",
        "https://github.com/KhronosGroup/OpenCL-CLHPP/archive/refs/tags/v2.0.13.tar.gz": "2020.12.18",
        "https://github.com/KhronosGroup/OpenCL-CLHPP/archive/refs/tags/v2.0.12.tar.gz": "2020.06.16",
        "https://github.com/KhronosGroup/OpenCL-CLHPP/archive/refs/tags/v2.0.11.tar.gz": "2020.03.13",

        "https://sqlite.org/2023/sqlite-amalgamation-3440200.zip": "3.44.2",
        "https://sqlite.org/2023/sqlite-amalgamation-3440100.zip": "3.44.1",
        "https://sqlite.org/2023/sqlite-amalgamation-3430200.zip": "3.43.2",
        "https://sqlite.org/2023/sqlite-amalgamation-3430100.zip": "3.43.1",
        "https://sqlite.org/2023/sqlite-amalgamation-3410200.zip": "3.41.2",
        "https://sqlite.org/2023/sqlite-amalgamation-3410100.zip": "3.41.1",
        "https://sqlite.org/2022/sqlite-amalgamation-3400100.zip": "3.40.1",
        "https://sqlite.org/2022/sqlite-amalgamation-3390400.zip": "3.39.4",
        "https://sqlite.org/2022/sqlite-amalgamation-3390300.zip": "3.39.3",
        "https://sqlite.org/2022/sqlite-amalgamation-3390200.zip": "3.39.2",
        "https://sqlite.org/2022/sqlite-amalgamation-3390100.zip": "3.39.1",
        "https://sqlite.org/2022/sqlite-amalgamation-3380500.zip": "3.38.5",
        "https://sqlite.org/2022/sqlite-amalgamation-3370200.zip": "3.37.2",

        "https://github.com/TartanLlama/expected/archive/6fe2af5191214cce620899f7f06585c047b9f1fc.zip": "20190710",

    }.get(url, "") == version


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
            elif not in_allow_list(version, url):
                versions_not_in_url.append((version, url))

        response = test_url(url)
        if response is None:
            print(f"url {url} is not available\n")
        elif not response.is_success:
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
