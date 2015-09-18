'''
   Parsedom for XBMC plugins
   Copyright (C) 2010-2011 Tobias Ussing And Henrik Mosgaard Jensen

   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
import os
import sys
import urllib
import urllib2
import re
import io
import inspect
import time
#import chardet
import json

plugin = sys.modules["__main__"].plugin
dbglevel = sys.modules["__main__"].dbglevel
size_modifier = 1.0
lastpct = 0


USERAGENT = u"Mozilla/5.0 (Windows NT 6.2; Win64; x64; rv:16.0.1) Gecko/20121011 Firefox/16.0.1"


if hasattr(sys.modules["__main__"], "opener"):
    urllib2.install_opener(sys.modules["__main__"].opener)



def fetchPage(params={}, write_fd=None):
    get = params.get
    link = get("link")
    log("link")
    log(link)
    ret_obj = { "new_url": link}


    request = urllib2.Request(link)

    if get("headers"):
        for head in get("headers"):
            log("Adding header: " + repr(head[0]) + " : " + repr(head[1]))
            request.add_header(head[0], head[1])

#    request.add_header('User-Agent', USERAGENT)



    try:
        log("connecting to server...", 1)

        con = urllib2.urlopen(request)
        ret_obj["header"] = con.info().headers
        ret_obj["new_url"] = con.geturl()

        if get("progress"):
            data = None
            data_len = 0
            tdata = ""
            totalsize = int(get("totalSize"))
            chunksize = totalsize / 100
            chunksize = 4096
            if chunksize < 4096:
                chunksize = 4096
            log("reading with progress", 1)
            while data_len == 0 or len(tdata) > 0:
                tdata = con.read(chunksize)
                data_len += len(tdata)
                if write_fd is not None:
                    write_fd.write(tdata)
                else:
                    if not data:
                        data = tdata
                    else:
                        data += tdata
                    assert(data_len == len(data))
                progress(totalsize, data_len)
            ret_obj["content"] = data
        else:
            log("reading", 1)
            ret_obj["content"] = con.read()

        con.close()

        log("Done")
        ret_obj["status"] = 200
        return ret_obj

    except urllib2.HTTPError, e:
        err = str(e)
        log("HTTPError : " + err)
        log("HTTPError - Headers: " + str(e.headers) + " - Content: " + repr(e.fp.read()))

        params["error"] = str(int(get("error", "0")) + 1)
        ret = fetchPage(params)

        if not "content" in ret and e.fp:
            ret["content"] = e.fp.read()
            return ret

        ret_obj["status"] = 500
        return ret_obj

    except urllib2.URLError, e:
        err = str(e)
        log("URLError : " + err)

        time.sleep(3)
        params["error"] = str(int(get("error", "0")) + 1)
        ret_obj = fetchPage(params)
        return ret_obj





def log(description, level=0):
    if dbglevel > level:
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        try:
            data = " %s [%s] %s : '%s'" % (timestamp, plugin, inspect.stack()[1][3], description)
        except:
            data = " FALLBACK %s [%s] %s : '%s'" % (timestamp, plugin, inspect.stack()[1][3], repr(description))

        sys.stderr.write(data + "\n")


## Git annex interface

last_progress_time = None
def progress(size=None, progress=None):
    global last_progress_time
    now = time.time()
    if last_progress_time is None or now - last_progress_time >= 1 or size == progress or progress == 0:
        last_progress_time = now
        sprint("PROGRESS %d" % (progress))

def sprint(txt):
    try:
        sys.stdout.write(txt + "\n")
        sys.stdout.flush()
    except:
        pass

def getCreds():
    log("", 3)
    creds = ask('GETCREDS mycreds').split(" ")
    log("Done: " + repr(creds), 3)
    return creds

def getConfig(key):
    log(key, 3)
    value = ask('GETCONFIG ' + key).replace("VALUE ", "")
    log("Done: " + repr(value), 3)
    return value

def ask(question):
    sprint(question)
    value = sys.stdin.readline().replace("\n", "")
    return value

def updateWanted(size, filetypes):
    log(repr(size) + " - " + repr(filetypes))
    old_wanted = ask("GETWANTED")

    log("old_wanted: " + repr(old_wanted))
    org_size = -1
    if old_wanted.find("largerthan") > -1:
        org_size = old_wanted[old_wanted.find("(not largerthan=") + len("(not largerthan="):]
        org_size = org_size[:org_size.find(")")]
        try:
            org_size = int(org_size.strip())
        except Exception as e:
            log("Exception: " + repr(e))

    expr = ""
    if filetypes:
        expr += "("
        org_filetypes = re.compile("include=(.*?) ").findall(old_wanted)
        for t in filetypes:
            expr += "include=*." + t + " or " 
        expr = expr.strip()
        if expr.rfind(" ") > -1:
            expr = expr[:expr.rfind(" ")]
        expr += ") and "

    if size or org_size:
        if size and (org_size == -1 or org_size > size):
            if len(expr) == 0:
                expr += "include=* and "
            log("Updating exclude size: " + repr(org_size) + " - " + repr(size))
            expr += "(not largerthan=" + str(size) + ")"
        elif org_size > -1:
            if len(expr) == 0:
                expr += "include=* and "
            log("New failing size is not smaller than already excluded size: " + repr(org_size) + " - " + repr(size))
            expr += "(not largerthan=" + str(org_size) + ")"


    if not len(expr):
        expr = "include=*"

    log("SETWANTED " + expr)
    sprint("SETWANTED " + expr)

    log("Done")

def sendError(msg):
    sprint("ERROR " + msg)

def startRemote():
    log("")
    sprint("VERSION 1")
    line = "initial"
    while len(line):
        line = sys.stdin.readline()
        line = line.strip().replace("\n", "")
        if len(line) == 0:
            log("Error, got empty line")
            continue

        line = line.split(" ")

        if line[0] == "INITREMOTE":
            sys.modules["__main__"].initremote(line)
        elif line[0] == "PREPARE":
            sys.modules["__main__"].prepare(line)
        elif line[0] == "TRANSFER":
            sys.modules["__main__"].transfer(line)
        elif line[0] == "CHECKPRESENT":
            sys.modules["__main__"].checkpresent(line)
        elif line[0] == "REMOVE":
            sys.modules["__main__"].remove(line)
        elif line[0] == "GETCOST":
            sys.modules["__main__"].getCost()
        elif line[0] == "ERROR":
            log("Git annex reported an error: " + "".join(line[1:]), -1)
            log("I don't know what to do about that, so i'm quitting", -1)
            sys.exit(1)
        else:
            log(repr(line), -1)
            sprint('UNSUPPORTED-REQUEST')
    log("Done: " + repr(line))
