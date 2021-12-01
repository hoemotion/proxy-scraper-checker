<h1 align="center">proxy-scraper-checker [simple-output]</h1>
<p align="center"><img src="screenshot.png" alt="Screenshot" /></p>

Check free anonymous HTTP, SOCKS4, SOCKS5 proxies from different sources. Supports determining exit-node's geolocation for each proxy.

**For a version with fancy output powered by [rich](https://github.com/willmcgugan/rich), see the [main](https://github.com/monosans/proxy-scraper-checker) branch.**

## Usage

- Make sure `Python` version is 3.7 or higher.
- Install dependencies from `requirements.txt` (`pip install -r requirements.txt`).
- Edit `config.py` according to your preference.
- Run `main.py`.

## Folders description

When the script finishes running, the following folders will be created:

- `proxies` - proxies with any anonymity level.

- `proxies_anonymous` - anonymous proxies.

- `proxies_geolocation` - same as `proxies`, but including exit-node's geolocation.

- `proxies_geolocation_anonymous` - same as `proxies_anonymous`, but including exit-node's geolocation.

Geolocation format is ip:port::Country::Region::City.

## Buy me a coffee

Ask for details in [Telegram](https://t.me/monosans) or [VK](https://vk.com/id607137534).

## License

[MIT](LICENSE)

This product includes GeoLite2 data created by MaxMind, available from http://www.maxmind.com.
