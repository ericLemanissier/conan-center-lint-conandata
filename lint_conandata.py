import logging
import os
import sys
import yaml

def iterate_urls(node):
    for version, version_data in node.items():
        if 'sha256' in version_data:
            url = version_data['url']
            sha = version_data['sha256']
            if isinstance(url, str):
                yield version, url, sha
            else:
                for u in url:
                    yield version, u, sha


def main(path: str) -> int:
    if path.endswith('conandata.yml'):
        path = path[0:-13]
    with open(os.path.join(path, 'conandata.yml'), encoding='utf-8') as file:
        conandata = yaml.safe_load(file)

    shas = {}
    urls = []
    version_in_url = None

    link = f"[{path}](https://github.com/conan-io/conan-center-index/tree/HEAD/recipes/{path}conandata.yml)"

    
    for version,url, sha in iterate_urls(conandata['sources']):

        if sha in shas and shas[sha] != version:
            logging.error("sha256 %s is present twice in %s (version %s)", sha, link, version)
        else:
            shas[sha] = version
        
        if url in urls:
            logging.error("url %s is present twice in %s (version %s)", url, link, version)
        else:
            urls.append(url)
           
        if url.startswith("http://"):
            logging.debug("url %s uses non secure http in %s", url, link)
        elif not url.startswith("https://"):
            logging.warning("unknown url scheme %s in %s", url, link) 

        version = version.lower()
        url = url.lower()
        if not version.startswith("cci."):
            b = (version in url) or (version.replace('.', '') in url)
            if version_in_url is None:
                version_in_url = b
            else:
                if b != version_in_url:
                    logging.error("some urls do not contain version in %s", link)
                    break

    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main('.'))    
    sys.exit(main(sys.argv[1]))