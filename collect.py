import os
import re
import shlex
import sqlite3
import subprocess

from datetime import datetime

here = os.path.abspath(os.path.dirname(__file__))
websites_dir = os.path.join(here, "websites")

class ArchivedFile(object):
    def __init__(self, filename, sha1, size, hostname, archived_at):
        self.filename = filename
        self.sha1 = sha1
        self.size = size
        self.hostname = hostname
        self.archived_at = archived_at

    def __str__(self):
        fmt = ("ArchivedFile\n"
               "  Name: %s\n"
               "  Size: %d\n"
               "  SHA1: %s\n"
               "  Host: %s\n"
               "  Archived At: %s\n")
        return fmt % (self.filename, self.size, self.sha1, self.hostname, self.archived_at)

def sha1_file(filename):
    out = subprocess.check_output("sha1sum %s" % shlex.quote(filename), shell=True)
    return re.findall('[a-f0-9]{40}', out.decode('utf-8','ignore'))[0]

def find_archived_files():
    archived_files = []
    for root, dirs, basenames in os.walk(websites_dir):
        for basename in basenames:
            filename = os.path.join(root, basename)
            filesize = os.path.getsize(filename)
            parts = os.path.split(filename)

            # ['members.lycos.co.uk', '20081010162854', 'leeedavison', '6502', 'eurobeeb', 'score', 'index.html']
            parts = filename.replace(websites_dir,'').strip(os.path.sep).split(os.path.sep)

            hostname = parts[0]

            datetime_str = parts[1]
            matches = re.findall('\d{14}', datetime_str) # "YYYYMMDDHHMMSS"
            if matches:
                archived_at = datetime.strptime(datetime_str, "%Y%m%d%H%M%S")
            else:
                raise Exception("Unable to parse date: %s" % filename)

            hidden_file = False
            for part in parts:
                if part.startswith("."):
                    hidden_file = True

            if not hidden_file:
                af = ArchivedFile(filename=filename, hostname=hostname, size=filesize, sha1=sha1_file(filename), archived_at=archived_at)
                print(af)
                archived_files.append(af)
    return archived_files

def create_database(filename, archived_files):
    if os.path.exists(filename):
        os.remove(filename)
    con = sqlite3.connect(filename)

    cur = con.cursor()
    cur.execute("create table archived_files (filename text, hostname text, size integer, sha1 char(20), archived_at datetime)")

    sql = ("insert into archived_files (filename, hostname, size, sha1, archived_at)"
           " values (?, ?, ?, ?, ?)")
    for af in archived_files:
        values = (af.filename, af.hostname, af.size, af.sha1, af.archived_at)
        cur.execute(sql, values)
    con.commit()



archived_files = find_archived_files()
create_database("database.sqlite3", archived_files)
