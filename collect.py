import os
import re
import shlex
import sqlite3
import subprocess

from datetime import datetime

here = os.path.abspath(os.path.dirname(__file__))
websites_dir = os.path.join(here, "websites")

class ArchivedFile(object):
    def __init__(self, filename, sha1, size, hostname, remote_filename, archived_at):
        self.filename = filename
        self.sha1 = sha1
        self.size = size
        self.hostname = hostname
        self.remote_filename = remote_filename
        self.archived_at = archived_at

    def __str__(self):
        fmt = ("ArchivedFile\n"
               "  Local Filename: %s\n"
               "  Remote Filename: %s\n"
               "  Size: %d\n"
               "  SHA1: %s\n"
               "  Host: %s\n"
               "  Archived At: %s\n")
        return fmt % (self.filename, self.remote_filename, self.size, self.sha1, self.hostname, self.archived_at)

def sha1_file(filename):
    out = subprocess.check_output("sha1sum %s" % shlex.quote(filename), shell=True)
    return re.findall('[a-f0-9]{40}', out.decode('utf-8','ignore'))[0]

def analyze_file(filename):
    out = subprocess.check_output("file %s" % shlex.quote(filename), shell=True)
    return out.decode('utf-8', 'ignore')

def zipfile_is_intact(filename):
    out = subprocess.check_output("unzip -t %s" % shlex.quote(filename), shell=True)
    return "No errors detected" in out.decode('utf-8', 'ignore')

def find_archived_files():
    archived_files = []
    for root, dirs, basenames in os.walk(websites_dir):
        for basename in basenames:
            filename = os.path.join(root, basename)
            filesize = os.path.getsize(filename)
            parts = os.path.split(filename)

            # ['members.lycos.co.uk', '20081010162854', 'leeedavison', '6502', 'eurobeeb', 'score', 'index.html']
            parts = filename.replace(websites_dir,'').strip(os.path.sep).split(os.path.sep)

            # ignore hidden files like .DS_Store
            if True in [ part.startswith(".") for part in parts ]:
                continue

            # 'members.lycos.co.uk'
            hostname = parts[0]

            # date of archive.org capture
            datetime_str = parts[1]
            matches = re.findall('\d{14}', datetime_str) # "YYYYMMDDHHMMSS"
            if matches:
                archived_at = datetime.strptime(datetime_str, "%Y%m%d%H%M%S")
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
            print(af)
            archived_files.append(af)
    return archived_files

def remove_corrupt_archived_files(archived_files):
    uncorrupted_files = []
    for af in archived_files:
        corrupt = False

        for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
            if af.filename.lower().endswith(ext):
                analysis = analyze_file(af.filename)
                if ("image data" not in analysis) and ("PC bitmap" not in analysis):
                    print("Corrupt image: %s" % af.filename)
                    corrupt = True

        if af.filename.lower().endswith('.zip'):
            if 'Zip archive data' not in analyze_file(af.filename):
                print("Not a ZIP file: %s" % af.filename)
                corrupt = True
            elif not zipfile_is_intact(af.filename):
                print("Corrupted ZIP file: %s" % af.filename)
                corrupt = True

        with open(af.filename, 'rb') as f:
            data = f.read()
            if b'HiringJobTweets' in data:
                print("Corrupt file (HiringJobTweets): %s" % af.filename)
                corrupt = True

            if b'orthopedic DME products' in data:
                print("Corrupt file (orthopedic DME products): %s" % af.filename)
                corrupt = True

            if af.filename.endswith(".html"):
                if (b'<body' in data) or (b'<BODY' in data):
                    if (b'</body' not in data) and (b'</BODY' not in data):
                        print("Corrupt HTML file (truncated): %s" % af.filename)
                        corrupt = True


        if not corrupt:
            uncorrupted_files.append(af)
    return uncorrupted_files

def create_database(filename, archived_files):
    if os.path.exists(filename):
        os.remove(filename)
    con = sqlite3.connect(filename)

    cur = con.cursor()
    cur.execute("create table archived_files ("
                 "filename text, "
                 "hostname text, "
                 "remote_filename text, "
                 "size integer, "
                 "sha1 char(20), "
                 "archived_at datetime)")

    sql = ("insert into archived_files (filename, hostname, remote_filename, size, sha1, archived_at)"
           " values (?, ?, ?, ?, ?, ?)")
    for af in archived_files:
        values = (af.filename, af.hostname, af.remote_filename, af.size, af.sha1, af.archived_at)
        cur.execute(sql, values)
    con.commit()


archived_files = find_archived_files()
archived_files = remove_corrupt_archived_files(archived_files)
create_database("database.sqlite3", archived_files)
