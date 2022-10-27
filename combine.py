import re
import shutil
import sqlite3
import os

con = sqlite3.connect("database.sqlite3")
cur = con.cursor()

cur.execute("drop table if exists filtered_files")
cur.execute("create table filtered_files AS select * from archived_files where 0")
con.commit()

# first we insert the latest file from mycorner, which was lee's last website
cur.execute("delete from filtered_files")
cur.execute("""
    INSERT INTO filtered_files
        SELECT
            AF.*
        FROM
            (SELECT filename, remote_filename, max(archived_at) AS latest
              FROM archived_files
              WHERE lower(hostname) like '%corner%'
              GROUP BY remote_filename
            ) subq
        INNER JOIN
          archived_files AF ON subq.filename = AF.filename AND subq.latest = AF.archived_at;
""")
con.commit()

# now we merge in the latest file from any of his previous sites
cur.execute("""
    INSERT INTO filtered_files
    SELECT
        AF.*
    FROM
        (SELECT filename, remote_filename, max(archived_at) AS latest
          FROM archived_files
          WHERE lower(hostname) not like '%corner%'
          and remote_filename in (
              select distinct(archived_files.remote_filename)
              from archived_files
              where archived_files.remote_filename not in (
                select distinct(filtered_files.remote_filename) from filtered_files
              )
          )
          GROUP BY remote_filename
        ) subq
    INNER JOIN
      archived_files AF ON subq.filename = AF.filename AND subq.latest = AF.archived_at;
""")
con.commit()


here = os.path.abspath(os.path.dirname(__file__))
combined_dir = os.path.join(here, "combined")


def remove_junk_outside_of_html_tags(data):
    # see: members.lycos.co.uk/20090226165902/leeedavison/misc/vfd/proto.html
    start_tag = b'<HTML>'
    idx = data.find(start_tag)
    if idx != -1:
        leading_stuff = data[0:idx].decode('utf-8', 'ignore')
        if re.findall('[^\s]', leading_stuff):
            print("   Removed junk before <HTML> tag")
            data = data[idx:] + b'\n'

    end_tag = b'</HTML>'
    idx = data.find(end_tag)
    if idx != -1:
        trailing_idx = idx + len(end_tag)
        trailing_stuff = data[trailing_idx:].decode('utf-8', 'ignore')
        if re.findall('[^\s]', trailing_stuff):
            print("   Removed junk after </HTML> tag")
            data = data[:trailing_idx] + b'\n'

    return data


sql = "select filename, remote_filename from filtered_files"
cur.execute(sql)
for filename, remote_filename in cur:
    src_filename = filename
    dest_filename = os.path.join(combined_dir, remote_filename)
    dest_dir = os.path.dirname(dest_filename)
    os.makedirs(dest_dir, exist_ok=True)
    print("Copy: %s -> %s" % (src_filename, dest_filename))
    shutil.copyfile(src_filename, dest_filename)

    if dest_filename.endswith(".html"):
        with open(dest_filename, "rb") as f:
            data = f.read()

        data = remove_junk_outside_of_html_tags(data)
        with open(dest_filename, "wb") as f:
            f.write(data)
