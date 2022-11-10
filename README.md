# Rebuilding Lee Davison's Website

> ⚠️ *If you have any backups of Lee Davison's website from any time period, or
if you downloaded any individual files from his website, please [get in touch](https://github.com/mnaberez) via email or [open an issue](https://github.com/6502org/mycorner/issues) on this repository. Many files are still missing and we need your help to find them.* ⚠️

Lee Davison [passed away](http://forum.6502.org/viewtopic.php?f=5&t=3024) on September 21, 2013.  When news of his passing spread months later, Lee's website was already down.  No complete backup of the last version of his website is known to exist.  This project rebuilds Lee's website by combining all files that have been found.

## Approach

Lee's website was online for over a decade.  Over the years, it had these hosts:

 - `http://mycorner.no-ip.org/` (most recent)
 - `http://themotionstore.com/leeedavison/`
 - `http://members.lycos.co.uk/leeedavison/`
 - `http://members.multimania.co.uk/leeedavison/`
 - `http://www.geocities.com/leeedavison/`

All available captures of these websites have been downloaded and stored in [`archives/`](./archives)
in this repository.  A build script indexes all files and then combines them into a single website.  The most recent copy of each file, based on the capture date, is used.  Special preference is given to files from `mycorner.no-ip.org`.  Many truncated or otherwise corrupted files are removed.  Tracking and advertising JavaScript inserted into the pages by the free web hosts is also removed.

The result is imperfect and many files are still missing.  However, it is the most complete collection of Lee's work that we have.  Files from all the various hosts and years ended up being used.  Lee helpfully put a "Last updated" date in the footer of all pages.

## Build

Building the reconstructed website requires a Unix-like system with GNU Make and Python 3.8 or later.  On Ubuntu 20.04 LTS, this command will install the requirements:

```text
sudo apt install build-essential python3
```

Run `make` from the root of this repository to build:

```text
$ make
```

The files will be written to `build/`.  The website should work if the local file `build/index.html` is opened in a browser.  Alternatively, Python's built-in webserver can be used:

```text 
$ python3 -m http.server --bind 127.0.0.1 --directory build/ 8000
```

Open a browser to `http://127.0.0.1:8000`.

## Credits

The following captures were used in this project:

 - [Hans Otten](http://retro.hansotten.nl) - Published a [reformatted](http://retro.hansotten.nl/6502-sbc/lee-davison-web-site/) version of Lee's 6502 pages and provided us with multiple captures of the website that he made over the years.  Exact dates and times are known because of comments embedded by the "HTTrack" scraper, e.g. `20090117205334`.

 - [Phil Pemberton](https://www.philpem.me.uk/) - Published his [capture](https://www.philpem.me.uk/leeedavison/) of Lee's website.  The exact time of capture is unknown.  These files have been given a capture date/time of `20030604000000`, since 2003-06-04 is the most recent date found in the "Last updated" footer of the pages.

 - [Wayback Machine](https://archive.org/web/) - Provided many other captures.  Although no captures were complete and many files had silent corruption, it contained some files there were not found anywhere else.
