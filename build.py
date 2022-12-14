#!/usr/bin/env python3

import datetime
import hashlib
import os
import re
import shlex
import shutil
import sqlite3
import subprocess


class ArchivedFile(object):
    """
    A single file from one of the captures, such as:
    mycorner.no-ip.org/20130212062031/6502/memoryplus/index.html
    """
    def __init__(self, filename, hostname, remote_filename, archived_at, html_footer_updated_at=None,
                 corruption=None, size_raw=None, sha1_raw=None, size_sanitized=None, sha1_sanitized=None,):
        self.filename = filename
        self.size_raw = size_raw
        self.sha1_raw = sha1_raw
        self.size_sanitized = size_sanitized
        self.sha1_sanitized = sha1_sanitized
        self.hostname = hostname
        self.remote_filename = remote_filename
        self.archived_at = archived_at
        self.html_footer_updated_at = html_footer_updated_at
        self.corruption = corruption

    @staticmethod
    def find_all_under_directory(archives_dir, progressfunc=None):
        """
        Walk a directory tree and collect any archived files it contains.  The
        tree must have the structure: archive/hostname/YYYYMMDDHHMMSS/.../filename
        """
        archived_files = []
        for root, dirs, basenames in os.walk(archives_dir):
            for basename in basenames:
                filename = os.path.join(root, basename)
                filesize = os.path.getsize(filename)
                parts = os.path.split(filename)

                # ['archive.org', 'members.lycos.co.uk', '20081010162854', 'leeedavison', '6502', 'eurobeeb', 'score', 'index.html']
                parts = filename.replace(archives_dir, '').strip(os.path.sep).split(os.path.sep)

                # ignore a README file in the root or under an archive subdir, e.g. "README.md" or "github.com/README.md"
                if (len(parts) < 3) and parts[-1].lower().startswith("readme"):
                    continue

                # ignore hidden files like .DS_Store
                if True in [ part.startswith(".") for part in parts ]:
                    continue

                # validate filename parts.  this directory from archive.org had trailing garbage:
                # "themotionstore.com/20081120030152/leeedavison/6502/eurobeeb/>"
                for part in parts:
                    if not re.match('^[a-zA-Z0-9\.,_-]+$', part):
                        raise Exception("Filename contains disallowed chars: %r" % filename)

                # 'members.lycos.co.uk'
                hostname = parts[1]

                # date of capture
                datetime_str = parts[2]
                matches = re.findall(r'\d{14}', datetime_str) # "YYYYMMDDHHMMSS"
                if matches:
                    archived_at = datetime.datetime.strptime(datetime_str, "%Y%m%d%H%M%S")
                else:
                    raise Exception("Unable to parse date: %s" % filename)

                # '6502/eurobeeb/score/index.html'
                if parts[3] == "leeedavison": # all sites except mycorner
                    parts.pop(0)
                remote_filename = '/'.join(parts[3:])

                af = ArchivedFile(filename=filename,
                                  hostname=hostname,
                                  remote_filename=remote_filename,
                                  archived_at=archived_at)
                af.analyze()
                if progressfunc is not None:
                    progressfunc(af)
                    if af.corruption is not None:
                        progressfunc("%s: %s" % (af.corruption, af.filename))
                    if af.sha1_raw != af.sha1_sanitized:
                        progressfunc("Sanitization required: %s" % af.filename)

                archived_files.append(af)
        return archived_files

    def __str__(self):
        return "ArchivedFile: %s" % self.filename

    def analyze(self):
        self.size_raw = len(self.read_raw())
        self.compute_sha1_raw()
        self.size_sanitized = len(self.read_sanitized())
        self.compute_sha1_sanitized()
        self.parse_html_footer_updated_at()
        self.detect_corruption()

    def detect_corruption(self):
        """Analyzes file on disk for corruption, sets self.corruption to a
        string if the file is corrupt."""
        self.corruption = None

        bad_sha1_raws = (
            # archives/archive.org/members.lycos.co.uk/20080725160852/leeedavison/6502/vic20/prgread/example.txt
            # basic program is truncated in the middle of line 10
            "98227581f6201bf8250df2d7964672deb7ea8ce9",

            # archives/retro.hansotten.nl/members.lycos.co.uk/20090811004900/leeedavison/6502/suprchips/lcd/asm.html
            # assembly listing corrupted by webstripper is not recoverable
            "e36b24626cd09f4e260de937b5d894b332d9df94",
        )
        assert self.sha1_raw is not None, "SHA-1 must be computed before calling"
        if self.sha1_raw in bad_sha1_raws:
            self.corruption = "Corrupt file: SHA-1 in list of known bad"
            return

        for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
            if self.filename.lower().endswith(ext):
                filetype = file_file(self.filename)
                if ("image data" not in filetype) and ("PC bitmap" not in filetype):
                    self.corruption = "Corrupt image"
                    return

        if self.filename.lower().endswith('.zip'):
            if 'Zip archive data' not in file_file(self.filename):
                self.corruption = "Corrupt ZIP file (not a ZIP)"
                return

            if not zipfile_is_intact(self.filename):
                self.corruption = "Corrupt ZIP file (not intact)"
                return

        with open(self.filename, 'rb') as f:
            data = f.read()

            for fragment in (
                b'HiringJobTweets',
                b'orthopedic DME products',
                b'jobtweets',
                b'extremetracking',
                b'lightspeedwebstore',
                b'nginx',
            ):
                if fragment in data:
                    self.corruption = "Corrupt file: (has fragment %r)" % fragment
                    return

            if self.filename.endswith(".html"):
                if (b'<body' in data) or (b'<BODY' in data):
                    if (b'</body' not in data) and (b'</BODY' not in data):
                        self.corruption = "Corrupt HTML file (truncated)"
                        return

    def compute_sha1_raw(self):
        h = hashlib.sha1()
        h.update(self.read_raw())
        self.sha1_raw = h.hexdigest()

    def read_raw(self):
        with open(self.filename, "rb") as f:
            return f.read()

    def compute_sha1_sanitized(self):
        h = hashlib.sha1()
        h.update(self.read_sanitized())
        self.sha1_sanitized = h.hexdigest()

    def parse_html_footer_updated_at(self):
        if not self.filename.endswith('html'):
            return

        # Footer of most HTML files:
        # b"<FONT SIZE=-1>Last page update: 2nd May, 2002.</FONT>"
        matches = re.findall(
            br'Last\s+page\s+update:\s+(\d+)\w{2}\s+([a-zA-Z]+)[,\s]+(\d{4})',
            self.read_sanitized()
            )
        if matches:
            matched_day, matched_month, matched_year = matches[0]

            day = int(matched_day)
            assert (day > 0) and (day < 32), "Invalid day: %r" % matched_day

            year = int(matched_year)
            assert (year > 1998) and (year < 2014), "Invalid year: %r" % matched_year

            month_names_to_nums = {
                b"January": 1, b"February": 2, b"March": 3, b"April": 4, b"May": 5, b"June": 6,
                b"July": 7, b"August": 8, b"September": 9, b"October": 10, b"November": 11, b"December": 12,
                # archives/archive.org/members.multimania.co.uk/20101019012340/leeedavison/6502/microchess/index.html
                b"Februaru": 2,
                # archives/archive.org/members.lycos.co.uk/20050413225556/leeedavison/68k/simbasic/index.html
                b'Februauy': 2,
                # archives/archive.org/members.lycos.co.uk/20030408075752/leeedavison/news.html
                b"pril": 4,
            }
            assert matched_month in month_names_to_nums, "Invalid month: %r" % matched_month
            month = month_names_to_nums[matched_month]

            self.html_footer_updated_at = datetime.datetime(year, month, day)

    def read_sanitized(self):
        pagedata = self.read_raw()

        if not self.filename.endswith('html'):
            return pagedata

        # Remove advertising and tracking scripts outside of <html>.  See:
        # archives/archive.org/members.lycos.co.uk/20090226165902/leeedavison/misc/vfd/proto.html
        for start_tag in (b'<HTML>', b'<html>'):
            idx = pagedata.find(start_tag)
            if idx != -1:
                leading_stuff = pagedata[0:idx].decode('utf-8', 'ignore')
                if re.findall(r'[^\s]', leading_stuff):
                    pagedata = pagedata[idx:]

        for end_tag in (b'</HTML>', b'</html>'):
            idx = pagedata.find(end_tag)
            if idx != -1:
                trailing_idx = idx + len(end_tag)
                trailing_stuff = pagedata[trailing_idx:].decode('utf-8', 'ignore')
                if re.findall(r'[^\s]', trailing_stuff):
                    pagedata = pagedata[:trailing_idx]

        # Remove HTTrack comments. See:
        # archives/retro.hansotten.nl/members.lycos.co.uk/20090117205334/leeedavison/index.html
        pagedata = re.sub(b'([\r\n]+<!-- Mirrored from.+HTTrack.*GMT -->[\r\n]+)', b'\n', pagedata)

        # Undo WebStripper changes.  See:
        # retro.hansotten.nl/members.lycos.co.uk/20090811004900/leeedavison/6502/ehbasic/update.html
        if b'webstripper' in pagedata:
            # remove onclick javascript
            for fullmatch in re.findall(br'(<(?:a|area)[^>]+href\s*=\s*"Dial Protected"[^>]+>)', pagedata):
                replacement = re.sub(br'(onclick\s*=\s*"[^"]+" )', b'', fullmatch)
                pagedata = pagedata.replace(fullmatch, replacement)

            # put values in "webstripperwas" and "webstripperlinkwas" back in their original attributes
            for regexp in (
                br'(<body\s+background\s*=\s*"([^"]+)"[^>]+webstripper(?:was|linkwas)\s*=\s*"([^"]+)"[^>]*>)',
                br'(<a\s+href="([^"]+)"[^>]+webstripper(?:was|linkwas)\s*=\s*"([^"]+)"[^>]*>)',
                br'(<img\s+src="([^"]+)"[^>]+webstripper(?:was|linkwas)\s*=\s*"([^"]+)"[^>]*>)',
            ):
                # put link in "webstripperlinkwas" back into its original attribute
                for fullmatch, orig, webstripperwas in re.findall(regexp, pagedata):
                    replacement = fullmatch.replace(orig, webstripperwas)
                    pagedata = pagedata.replace(fullmatch, replacement)

            # remove all "webstripperwas" and "webstripperlinkwas" attributes
            pagedata = re.sub(br'(\s*webstripper(?:was|linkwas)\s*=\s*"[^"]+)"', b'', pagedata)
        
        return pagedata


class Database(object):
    """
    SQLite database used to find the most recent version of each file.
    """
    def __init__(self, dbfile):
        self.con = sqlite3.connect(dbfile)
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()

    def build_table_of_all_archived_files(self, archived_files):
        """
        Given an iterable object of ArchivedFile instances,
        create the 'archived_files' table with one row for each.
        """
        self.cur.execute("DROP TABLE IF EXISTS archived_files")
        self.cur.execute("""
            CREATE TABLE archived_files (
                filename TEXT NOT NULL,
                hostname TEXT NOT NULL,
                remote_filename TEXT NOT NULL,
                size_raw INTEGER NOT NULL,
                sha1_raw CHAR(20) NOT NULL,
                size_sanitized INTEGER NOT NULL,
                sha1_sanitized CHAR(20) NOT NULL,
                archived_at DATETIME NOT NULL,
                html_footer_updated_at DATETIME, -- null if unknown or not html
                corruption TEXT -- null if not corrupt
            )
        """)
        self.con.commit()

        sql = """
            INSERT INTO archived_files (
                filename, hostname, remote_filename,
                size_raw, sha1_raw, size_sanitized, sha1_sanitized, archived_at,
                html_footer_updated_at, corruption
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for af in archived_files:
            values = (af.filename, af.hostname, af.remote_filename,
                      af.size_raw, af.sha1_raw, af.size_sanitized, af.sha1_sanitized,
                      af.archived_at, af.html_footer_updated_at, af.corruption)
            self.cur.execute(sql, values)
        self.con.commit()

    def build_table_with_latest_version_of_each_file(self):
        """
        Create the 'filterd_files' table from the 'archived_files' table.  This table
        will contain only the most recent, non-corrupted version of each file based
        on the capture date.  Priority is given to pages from mycorner.no-ip.org,
        since that was Lee's last host.
        """
        self.cur.execute("DROP TABLE IF EXISTS latest_files")
        self.cur.execute("CREATE TABLE latest_files AS SELECT * FROM archived_files WHERE 0")
        self.con.commit()

        # First we insert the latest files from Lee's last host: mycorner.no-ip.org
        self.cur.execute("""
            INSERT INTO latest_files
                SELECT
                    archived_files.*
                FROM (
                      SELECT filename, remote_filename, max(archived_at) AS latest
                      FROM archived_files
                      WHERE hostname = 'mycorner.no-ip.org'
                        AND corruption is NULL
                      GROUP BY remote_filename
                    ) subq
                INNER JOIN archived_files
                    ON subq.filename = archived_files.filename
                    AND subq.latest = archived_files.archived_at;
        """)
        self.con.commit()

        # Now we merge in the latest files from any of his previous hosts
        self.cur.execute("""
            INSERT INTO latest_files
            SELECT
                archived_files.*
            FROM (
                  SELECT filename, remote_filename, max(archived_at) AS latest
                  FROM archived_files
                  WHERE hostname <> 'mycorner.no-ip.org'
                    AND corruption is NULL
                  AND remote_filename IN (
                      SELECT DISTINCT(archived_files.remote_filename)
                      FROM archived_files
                      WHERE archived_files.remote_filename NOT IN (
                          SELECT DISTINCT(latest_files.remote_filename)
                          FROM latest_files
                      )
                  )
                  GROUP BY remote_filename
                ) subq
            INNER JOIN archived_files
                ON subq.filename = archived_files.filename
                AND subq.latest = archived_files.archived_at;
        """)
        self.con.commit()

    def _make_archived_file(self, sqlite3_row):
        attrs = dict(sqlite3_row)
        for k in [ k for k in attrs.keys() if k.endswith("_at") ]:
            if attrs[k] is not None:
                attrs[k] = datetime.datetime.strptime(attrs[k], "%Y-%m-%d %H:%M:%S")
        return ArchivedFile(**attrs)

    def find_latest_version_of_each_file(self):
        self.cur.execute("""
            SELECT * FROM latest_files
        """)
        for row in self.cur:
            yield self._make_archived_file(row)

    def find_all_versions_of_each_file(self):
        self.cur.execute("""
            SELECT DISTINCT remote_filename
            FROM archived_files
            WHERE corruption IS NULL
            ORDER BY remote_filename ASC
        """)
        distinct_remote_filenames = [ row[0] for row in self.cur ]

        for remote_filename in distinct_remote_filenames:
            self.cur.execute("""
                SELECT *
                FROM archived_files
                WHERE remote_filename = ?
                  AND corruption IS NULL
                GROUP BY sha1_sanitized
                ORDER BY size_sanitized DESC
            """, (remote_filename,))
            archived_files = [ self._make_archived_file(row) for row in self.cur ]
            yield (remote_filename, archived_files)


def rewrite_mailto_links(pagedata):
    # see "e-mail me" at the bottom of almost all html pages
    new_link = b"http://forum.6502.org/viewtopic.php?f=5&t=3024"
    for email in (
        b"leeedavison@googlemail.com",
        b"leeedavison@lycos.co.uk",
        b"leeedavison@yahoo.co.uk"
    ):
        old_link = b"mailto:" + email
        pagedata = pagedata.replace(old_link, new_link)
    return pagedata


def rewrite_page_links(pagedata):
    # see: mycorner.no-ip.org/20130214063757/news2001.html
    replaced = b''
    for linedata in pagedata.splitlines(keepends=True):
        lowered = linedata.lower()
        if (b'href' in lowered) or (b'refresh' in lowered):
            linedata = re.sub(b'(http://[^/]+/leeedavison/)', b'./', linedata, re.IGNORECASE)
        replaced += linedata
    return replaced


def rewrite_home_page(pagedata):
    search = b'<IMG SRC="view.jpg"BORDER=1 TITLE="View from my Southampton flat">'
    replace = b"""
        <p style="background-color: #ffffe0; margin-bottom: 7px; padding: 5px 5px 5px 5px; text-align: center;">
          Lee Davison <a target="_top" href="http://forum.6502.org/viewtopic.php?f=5&t=3024">passed away</a> on September 21, 2013.
          <br clear="all">
          6502.org hosts this <a target="_top" href="https://github.com/6502org/mycorner">reconstruction</a> of his website to preserve his memory and ensure the resources he created remain available.
        </p>
        <TR><TD COLSPAN=2 ALIGN=CENTER>
        <IMG SRC="view.jpg" BORDER=1 TITLE="View from my Southampton flat">
    """
    if search not in pagedata:
        raise Exception("Search text to replace on home page not found")
    return pagedata.replace(search, replace)


def file_file(filename):
    out = subprocess.check_output("file %s" % shlex.quote(filename), shell=True)
    return out.decode('utf-8', 'ignore')

def zipfile_is_intact(filename):
    out = subprocess.check_output("unzip -t %s" % shlex.quote(filename), shell=True)
    return "No errors detected" in out.decode('utf-8', 'ignore')


def main():
    here = os.path.abspath(os.path.dirname(__file__))
    archives_dir = os.path.join(here, "archives")
    build_dir = os.path.join(here, "build")
    dbfile = os.path.join(here, "database.sqlite3")

    # find all archived files on the filesystem
    archived_files = ArchivedFile.find_all_under_directory(archives_dir, progressfunc=print)

    # build a database of all archived files
    db = Database(dbfile)
    db.build_table_of_all_archived_files(archived_files)
    db.build_table_with_latest_version_of_each_file()

    # reconstruct the website by taking the latest non-corrupted version of each file
    shutil.rmtree(build_dir, ignore_errors=True)
    for archived_file in db.find_latest_version_of_each_file():
        src_filename = archived_file.filename

        dest_filename = os.path.join(build_dir, archived_file.remote_filename)
        dest_dir = os.path.dirname(dest_filename)
        os.makedirs(dest_dir, exist_ok=True)

        print("Copy: %s -> %s" % (src_filename, dest_filename))
        shutil.copyfile(src_filename, dest_filename)

        if dest_filename.endswith(".html"):
            pagedata = archived_file.read_sanitized()

            if archived_file.remote_filename == "index.html":
                pagedata = rewrite_home_page(pagedata)

            pagedata = rewrite_mailto_links(pagedata)
            pagedata = rewrite_page_links(pagedata)

            with open(dest_filename, "wb") as f:
                f.write(pagedata)

    # substitute missing files with older equivalents
    new_to_old = {
        # new                           # old
        '6502/acia/acia01s.jpg':        '6502/acia/acialeft.jpg',
        '6502/acia/acia02s.jpg':        '6502/acia/aciaright.jpg',
        '6502/atkey/atkey01s.jpg':      '6502/atkey/atkeyl.jpg',
        '6502/atkey/atkey02s.jpg':      '6502/atkey/atkeyr.jpg',
        '6502/i2c/i2c01s.jpg':          '6502/i2c/board.jpg',
        '6502/i2c/i2c02s.jpg':          '6502/i2c/plusteletext.jpg',
        '6502/i2c/ttx08s.jpg':          '6502/i2c/inuse.jpg',
        '6502/i2c/ttx01s.jpg':          '6502/i2c/ch5.jpg',
        '6502/i2c/ttx01.html':          '6502/i2c/ch5.html',
        '6502/i2c/ttx02s.jpg':          '6502/i2c/cnn.jpg',
        '6502/i2c/ttx02.html':          '6502/i2c/cnn.html',
        '6502/i2c/ttx03s.jpg':          '6502/i2c/dsny.jpg',
        '6502/i2c/ttx03.jpg':           '6502/i2c/dsny.jpg',
        '6502/i2c/ttx04s.jpg':          '6502/i2c/mtv.jpg',
        '6502/i2c/ttx04.html':          '6502/i2c/mtv.html',
        '6502/i2c/ttx05s.jpg':          '6502/i2c/nick.jpg',
        '6502/i2c/ttx05.html':          '6502/i2c/nick.html',
        '6502/i2c/ttx06s.jpg':          '6502/i2c/toon.jpg',
        '6502/i2c/ttx06.html':          '6502/i2c/toon.html',
        '6502/nopgen/nopgen01s.jpg':    '6502/nopgen/nopgen.jpg',
        '6502/nopgen/nopgen02s.jpg':    '6502/nopgen/32kram.jpg',
        '6502/nopgen/nopgen03s.jpg':    '6502/nopgen/phase2.jpg',
        '6502/nopgen/nopgen04s.jpg':    '6502/nopgen/32krom.jpg',
        '6502/nopgen/nopgen05s.jpg':    '6502/nopgen/inuse.jpg',
        '6502/projects.jpg':            '6502/project.jpg',
        '6502/smd/smd01s.jpg':          '6502/smd/smdleft.jpg',
        '6502/smd/smd02s.jpg':          '6502/smd/smdright.jpg',
    }
    for new, old in new_to_old.items():
        src_filename =  os.path.join(build_dir, old)
        dest_filename = os.path.join(build_dir, new)
        if not os.path.exists(dest_filename):
            print("Substitute: %s -> %s" % (src_filename, dest_filename))
            shutil.copyfile(src_filename, dest_filename)

if __name__ == '__main__':
    main()
