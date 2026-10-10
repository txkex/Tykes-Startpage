# Tyke's Startpage

A self-hosted browser start page with a dotted, animated look: web search, your links, a live clock, weather, moon phase, a spinning globe, live system stats with a spinning RTX 3060, and Windows now-playing music controls with a visualizer.

![Screenshot of the start page](screenshot.png)

## Features

- **Search bar** for SearXNG or Google. Click the logo to switch engine. Searches open in a new tab.
- **Links** in groups you edit as plain text. Links open in a new tab, and you can set your own logo per link (right-click, or long-press on touch).
- **Clock, weather, moon phase** with 12/24-hour time and °C/°F. Weather uses [Open-Meteo](https://open-meteo.com), no API key needed.
- **Globe** you can drag and spin: earth, solar system, Saturn, or a black hole. Double-click it to switch.
- **Live stats**: CPU, RAM, and (NVIDIA only) GPU load, VRAM, name and temperature, shown with a spinning dotted graphics card whose fans speed up with GPU load.
- **Music panel** with now playing, album art, play/pause/next/previous and an audio visualizer (Windows only).
- **Accent colors** (including rainbow) that recolor the whole page.
- Settings are saved in your browser, not on the server.

## Quick start with Docker

```
git clone https://github.com/txkex/Tyke-s-Startpage.git
cd Tyke-s-Startpage
docker compose up -d --build
```

Then open <http://localhost:8787>.

- The compose file also publishes port 80, so you can open the page without a port number. Delete that line in `docker-compose.yml` if port 80 is already in use on your machine.
- Docker shows CPU, RAM and (optionally) GPU stats. Music controls and the visualizer need Windows, because a container can't see your desktop's media session.
- **NVIDIA GPU stats:** install the NVIDIA Container Toolkit on the host and uncomment the GPU lines in `docker-compose.yml`.

## Quick start on Windows (no Docker)

1. Install [Python 3](https://www.python.org/downloads/) (tick "Add Python to PATH").
2. Double-click `startpage.pyw`. A tray icon appears and the first launch installs what it needs automatically.
3. Open <http://localhost:8787>.

The tray menu has previous/play/next, "Open start page", "View raw stats" and "Start with Windows". Problems are logged to `stats_server.log` next to the script.

## Settings

Click **[settings]** in the top right of the page to change the search engine, weather city, units, colors, time format, globe, and your list of links. In the links box, `# name` starts a group and each following line is `name url`.

Server options go in an optional `config.json` next to `server.py`, or in environment variables (copy `config_example.json` to start):

| Option | Default | What it does |
| --- | --- | --- |
| `host` | `127.0.0.1` (Docker: `0.0.0.0`) | Address to listen on |
| `port` | `8787` | Port to listen on |
| `open_url` | `http://localhost:<port>` | Address the tray's "Open start page" opens, e.g. `http://tyke.start` |
| `cors_origin` | none | A page address allowed to use this server from another host, for when the page runs on a NAS but the music helper runs on your desktop |

### Using a custom address like `http://tyke.start`

Add a line to your hosts file pointing the name at the machine running the page, then open `http://tyke.start`:

```
127.0.0.1 tyke.start
```

On Windows the file is `C:\Windows\System32\drivers\etc\hosts` and must be edited as administrator. Use your server's IP instead of `127.0.0.1` if the page runs on another machine.

## Server endpoints

| Path | What it returns |
| --- | --- |
| `/` | The start page |
| `/stats` | CPU, RAM and GPU as JSON |
| `/media` | Now playing: title, artist, album art (Windows) |
| `/media/<prev\|play_pause\|next>` | POST to control playback (Windows) |
| `/spectrum` | Live audio bands for the visualizer (Windows) |

## Notes

- Link icons are fetched from DuckDuckGo's icon service, and weather from Open-Meteo, so those two features need internet access.
- The server only accepts requests from its own page (and `cors_origin` if set), so other websites can't press your media buttons.

## License

Released under the [MIT License](LICENSE).
