#!/usr/bin/env python3

import datetime
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
    def __init__(self, filename, sha1, size, hostname, remote_filename, archived_at, corruption=None):
        self.filename = filename
        self.sha1 = sha1
        self.size = size
        self.hostname = hostname
        self.remote_filename = remote_filename
        self.archived_at = archived_at
        self.corruption = corruption

    @staticmethod
    def find_all_under_directory(websites_dir, progressfunc=None):
        """
        Walk a directory tree and collect any archived files it contains.  The
        tree must have the structure: hostname/YYYYMMDDHHMMSS/.../filename
        """
        archived_files = []
        for root, dirs, basenames in os.walk(websites_dir):
            for basename in basenames:
                filename = os.path.join(root, basename)
                filesize = os.path.getsize(filename)
                parts = os.path.split(filename)

                # ['members.lycos.co.uk', '20081010162854', 'leeedavison', '6502', 'eurobeeb', 'score', 'index.html']
                parts = filename.replace(websites_dir, '').strip(os.path.sep).split(os.path.sep)

                # ignore hidden files like .DS_Store
                if True in [ part.startswith(".") for part in parts ]:
                    continue

                # 'members.lycos.co.uk'
                hostname = parts[0]

                # date of archive.org capture
                datetime_str = parts[1]
                matches = re.findall('\d{14}', datetime_str) # "YYYYMMDDHHMMSS"
                if matches:
                    archived_at = datetime.datetime.strptime(datetime_str, "%Y%m%d%H%M%S")
                else:
                    raise Exception("Unable to parse date: %s" % filename)

                # '6502/eurobeeb/score/index.html'
                if parts[2] == "leeedavison": # all sites except mycorner
                    parts.pop(0)
                remote_filename = '/'.join(parts[2:])

                af = ArchivedFile(filename=filename,
                                  hostname=hostname,
                                  remote_filename=remote_filename,
                                  size=filesize,
                                  sha1=sha1_file(filename),
                                  archived_at=archived_at)

                af.detect_corruption()
                if progressfunc is not None:
                    progressfunc(af)
                    if af.corruption is not None:
                        progressfunc("%s: %s" % (af.corruption, af.filename))

                archived_files.append(af)
        return archived_files

    def __str__(self):
        return "ArchivedFile: %s" % self.filename

    def detect_corruption(self):
        """Analyzes file on disk for corruption, sets self.corruption to a
        string if the file is corrupt."""
        self.corruption = None

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

        def is_corrupt(self):
            return self.corruption is not None


class Database(object):
    """
    SQLite database used to find the most recent version of each file.
    """
    def __init__(self, dbfile):
        self.con = sqlite3.connect(dbfile)
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
                size INTEGER NOT NULL,
                sha1 CHAR(20) NOT NULL,
                archived_at DATETIME NOT NULL,
                corruption TEXT -- null if not corrupt
            )
        """)
        self.con.commit()

        sql = """
            INSERT INTO archived_files (
                filename, hostname, remote_filename,
                size, sha1, archived_at, corruption
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        for af in archived_files:
            values = (af.filename, af.hostname, af.remote_filename,
                      af.size, af.sha1, af.archived_at, af.corruption)
            self.cur.execute(sql, values)
        self.con.commit()

    def build_table_with_latest_version_of_each_file(self):
        """
        Create the 'filterd_files' table from the 'archived_files' table.  This table
        will contain only the most recent, non-corrupted version of each file based
        on the capture date.  Priority is given to pages from mycorner.no-ip.org,
        since that was Lee's last host.
        """
        self.cur.execute("DROP TABLE IF EXISTS filtered_files")
        self.cur.execute("CREATE TABLE filtered_files AS SELECT * FROM archived_files WHERE 0")
        self.con.commit()

        # First we insert the latest files from Lee's last host: mycorner.no-ip.org
        self.cur.execute("""
            INSERT INTO filtered_files
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
            INSERT INTO filtered_files
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
                          SELECT DISTINCT(filtered_files.remote_filename)
                          FROM filtered_files
                      )
                  )
                  GROUP BY remote_filename
                ) subq
            INNER JOIN archived_files
                ON subq.filename = archived_files.filename
                AND subq.latest = archived_files.archived_at;
        """)
        self.con.commit()

    def find_latest_version_of_each_file(self):
        sql = ""
        self.cur.execute("""
            SELECT filename, hostname, remote_filename, size, sha1, archived_at
            FROM filtered_files
        """)
        for filename, hostname, remote_filename, size, sha1, archived_at in self.cur:
            yield ArchivedFile(
                filename=filename,
                hostname=hostname,
                remote_filename=remote_filename,
                size=size,
                sha1=sha1,
                archived_at=archived_at)


def remove_junk_outside_of_html_tags(pagedata):
    # see: members.lycos.co.uk/20090226165902/leeedavison/misc/vfd/proto.html
    start_tag = b'<HTML>'
    idx = pagedata.find(start_tag)
    if idx != -1:
        leading_stuff = pagedata[0:idx].decode('utf-8', 'ignore')
        if re.findall('[^\s]', leading_stuff):
            print("   Removed junk before <HTML> tag")
            pagedata = pagedata[idx:] + b'\n'

    end_tag = b'</HTML>'
    idx = pagedata.find(end_tag)
    if idx != -1:
        trailing_idx = idx + len(end_tag)
        trailing_stuff = pagedata[trailing_idx:].decode('utf-8', 'ignore')
        if re.findall('[^\s]', trailing_stuff):
            print("   Removed junk after </HTML> tag")
            pagedata = pagedata[:trailing_idx] + b'\n'

    return pagedata


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


def sha1_file(filename):
    out = subprocess.check_output("sha1sum %s" % shlex.quote(filename), shell=True)
    return re.findall('[a-f0-9]{40}', out.decode('utf-8','ignore'))[0]

def file_file(filename):
    out = subprocess.check_output("file %s" % shlex.quote(filename), shell=True)
    return out.decode('utf-8', 'ignore')

def zipfile_is_intact(filename):
    out = subprocess.check_output("unzip -t %s" % shlex.quote(filename), shell=True)
    return "No errors detected" in out.decode('utf-8', 'ignore')


def main():
    here = os.path.abspath(os.path.dirname(__file__))
    websites_dir = os.path.join(here, "websites")
    combined_dir = os.path.join(here, "combined")
    dbfile = os.path.join(here, "database.sqlite3")

    # find all archived files on the filesystem
    archived_files = ArchivedFile.find_all_under_directory(websites_dir, progressfunc=print)

    # build a database of all archived files
    db = Database(dbfile)
    db.build_table_of_all_archived_files(archived_files)
    db.build_table_with_latest_version_of_each_file()

    # reconstruct the website by taking the latest non-corrupted version of each file
    shutil.rmtree(combined_dir, ignore_errors=True)
    for archived_file in db.find_latest_version_of_each_file():
        src_filename = archived_file.filename

        # missing file exists in older archives under a different name
        rf = archived_file.remote_filename
        if rf == '6502/project.jpg':
            rf = '6502/projects.jpg'

        dest_filename = os.path.join(combined_dir, rf)
        dest_dir = os.path.dirname(dest_filename)
        os.makedirs(dest_dir, exist_ok=True)

        print("Copy: %s -> %s" % (src_filename, dest_filename))
        shutil.copyfile(src_filename, dest_filename)

        if dest_filename.endswith(".html"):
            with open(dest_filename, "rb") as f:
                pagedata = f.read()

            if rf == "index.html":
                pagedata = rewrite_home_page(pagedata)

            pagedata = remove_junk_outside_of_html_tags(pagedata)
            pagedata = rewrite_mailto_links(pagedata)
            pagedata = rewrite_page_links(pagedata)

            with open(dest_filename, "wb") as f:
                f.write(pagedata)

if __name__ == '__main__':
    main()
