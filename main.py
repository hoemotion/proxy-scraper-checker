#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import logging
from ipaddress import IPv4Address
from os import mkdir
from random import shuffle
from shutil import rmtree
from typing import Any, Dict, Iterable, Optional, Tuple

from aiohttp import ClientSession
from aiohttp_socks import ProxyConnector
from maxminddb import open_database
from maxminddb.reader import Reader

import config


class ProxyScraperChecker:
    def __init__(
        self,
        *,
        max_connections: int = 950,
        timeout: float = 5,
        geolite2_city_mmdb: Optional[str] = None,
        ip_service: str = "https://checkip.amazonaws.com",
        http_sources: Optional[Iterable[str]] = None,
        socks4_sources: Optional[Iterable[str]] = None,
        socks5_sources: Optional[Iterable[str]] = None,
    ) -> None:
        """Scrape and check proxies from sources and save them to files.

        Args:
            max_connections (int): Maximum concurrent connections.
            timeout (float): How many seconds to wait for the connection.
            geolite2_city_mmdb (str): Path to the GeoLite2-City.mmdb if you
                want to add location info for each proxy.
            ip_service (str): Service for getting your IP address and checking
                if proxies are valid.
        """
        self.sem = asyncio.Semaphore(max_connections)
        self.IP_SERVICE = ip_service.strip()
        self.TIMEOUT = timeout
        self.MMDB = geolite2_city_mmdb
        self.SOURCES = {
            proto: (sources,)
            if isinstance(sources, str)
            else frozenset(sources)
            for proto, sources in (
                ("http", http_sources),
                ("socks4", socks4_sources),
                ("socks5", socks5_sources),
            )
            if sources
        }
        self.proxies: Dict[str, Dict[str, Optional[str]]] = {
            proto: {} for proto in self.SOURCES
        }
        self.proxies_count = {proto: 0 for proto in self.SOURCES}

    @staticmethod
    def append_to_file(file_path: str, content: str) -> None:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"{content}\n")

    @staticmethod
    def get_geolocation(ip: Optional[str], reader: Reader) -> str:
        """Get proxy's geolocation.

        Args:
            ip (str): Proxy's ip.
            reader (Reader): mmdb Reader instance.

        Returns:
            str: ::Country Name::Region::City
        """
        if not ip:
            return "::None::None::None"
        geolocation = reader.get(ip)
        if not isinstance(geolocation, dict):
            return "::None::None::None"
        country = geolocation.get("country")
        if country:
            country = country["names"]["en"]
        else:
            country = geolocation.get("continent")
            if country:
                country = country["names"]["en"]
        region = geolocation.get("subdivisions")
        if region:
            region = region[0]["names"]["en"]
        city = geolocation.get("city")
        if city:
            city = city["names"]["en"]
        return f"::{country}::{region}::{city}"

    async def fetch_source(
        self, session: ClientSession, source: str, proto: str
    ) -> None:
        """Get proxies from source.

        Args:
            source (str): Proxy list URL.
            proto (str): http/socks4/socks5.
        """
        try:
            async with session.get(source.strip(), timeout=15) as r:
                status = r.status
                text = await r.text(encoding="utf-8")
        except Exception as e:
            logging.error(f"{source}: {e}")
        else:
            if status == 200:
                for proxy in text.splitlines():
                    proxy = (
                        proxy.replace(f"{proto}://", "")
                        .replace("https://", "")
                        .strip()
                    )
                    try:
                        IPv4Address(proxy.split(":")[0])
                    except Exception:
                        continue
                    self.proxies[proto][proxy] = None
            else:
                logging.error(f"{source} status code: {status}")

    async def check_proxy(self, proxy: str, proto: str) -> None:
        """Check proxy validity.

        Args:
            proxy (str): ip:port.
            proto (str): http/socks4/socks5.
        """
        try:
            async with self.sem:
                async with ClientSession(
                    connector=ProxyConnector.from_url(f"{proto}://{proxy}")
                ) as session:
                    async with session.get(
                        self.IP_SERVICE, timeout=self.TIMEOUT
                    ) as r:
                        exit_node = await r.text(encoding="utf-8")
            exit_node = exit_node.strip()
            IPv4Address(exit_node)
        except Exception as e:

            # Too many open files
            if isinstance(e, OSError) and e.errno == 24:
                logging.error("Please, set MAX_CONNECTIONS to lower value.")

            self.proxies[proto].pop(proxy)
        else:
            self.proxies[proto][proxy] = exit_node

    async def fetch_all_sources(self) -> None:
        """Get proxies from sources."""
        logging.info("Fetching sources")
        async with ClientSession() as session:
            coroutines = (
                self.fetch_source(session, source, proto)
                for proto, sources in self.SOURCES.items()
                for source in sources
            )
            await asyncio.gather(*coroutines)
        for proto, proxies in self.proxies.items():
            self.proxies_count[proto] = len(proxies)

    async def check_all_proxies(self) -> None:
        for proto, proxies in self.proxies.items():
            logging.info(f"Checking {len(proxies)} {proto} proxies")
        coroutines = [
            self.check_proxy(proxy, proto)
            for proto, proxies in self.proxies.items()
            for proxy in proxies
        ]
        shuffle(coroutines)
        await asyncio.gather(*coroutines)

    def sort_proxies(self) -> None:
        self.proxies = {
            proto: dict(sorted(proxies.items(), key=self._get_sorting_key))
            for proto, proxies in self.proxies.items()
        }

    def save_proxies(self) -> None:
        """Delete old proxies and save new ones."""
        dirs_to_delete = (
            "proxies",
            "proxies_anonymous",
            "proxies_geolocation",
            "proxies_geolocation_anonymous",
        )
        for dir in dirs_to_delete:
            try:
                rmtree(dir)
            except FileNotFoundError:
                pass
        dirs_to_create = (
            dirs_to_delete if self.MMDB else ("proxies", "proxies_anonymous")
        )
        for dir in dirs_to_create:
            mkdir(dir)

        # proxies and proxies_anonymous folders
        for proto, proxies in self.proxies.items():
            path = f"proxies/{proto}.txt"
            path_anonymous = f"proxies_anonymous/{proto}.txt"
            for proxy, exit_node in proxies.items():
                self.append_to_file(path, proxy)
                if exit_node != proxy.split(":")[0]:
                    self.append_to_file(path_anonymous, proxy)

        # proxies_geolocation and proxies_geolocation_anonymous folders
        if self.MMDB:
            with open_database(self.MMDB) as reader:
                for proto, proxies in self.proxies.items():
                    path = f"proxies_geolocation/{proto}.txt"
                    path_anonymous = (
                        f"proxies_geolocation_anonymous/{proto}.txt"
                    )
                    for proxy, exit_node in proxies.items():
                        line = proxy + self.get_geolocation(exit_node, reader)
                        self.append_to_file(path, line)
                        if exit_node != proxy.split(":")[0]:
                            self.append_to_file(path_anonymous, line)

    async def main(self) -> None:
        await self.fetch_all_sources()
        await self.check_all_proxies()

        logging.info("Result:")
        for proto, proxies in self.proxies.items():
            logging.info(f"{proto} - {len(proxies)}")

        self.sort_proxies()
        self.save_proxies()

        logging.info(
            "Proxy folders have been created in the current directory."
        )
        logging.info("Thank you for using proxy-scraper-checker :)")

    @staticmethod
    def _get_sorting_key(x: Tuple[str, Any]) -> Tuple[int, ...]:
        octets = x[0].replace(":", ".").split(".")
        return tuple(map(int, octets))


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    await ProxyScraperChecker(
        max_connections=config.MAX_CONNECTIONS,
        timeout=config.TIMEOUT,
        geolite2_city_mmdb="GeoLite2-City.mmdb"
        if config.GEOLOCATION
        else None,
        ip_service=config.IP_SERVICE,
        http_sources=config.HTTP_SOURCES if config.HTTP else None,
        socks4_sources=config.SOCKS4_SOURCES if config.SOCKS4 else None,
        socks5_sources=config.SOCKS5_SOURCES if config.SOCKS5 else None,
    ).main()


if __name__ == "__main__":
    asyncio.run(main())
