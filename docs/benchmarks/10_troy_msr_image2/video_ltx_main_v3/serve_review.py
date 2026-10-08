#!/usr/bin/env python3
"""Loopback-only review server with byte ranges for long-video scrubbing."""
import argparse,functools,http.server,os,re
from pathlib import Path
class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        self.byte_range=None
        path=self.translate_path(self.path)
        if not os.path.isfile(path):return super().send_head()
        try:f=open(path,'rb')
        except OSError:self.send_error(404);return None
        stat=os.fstat(f.fileno());size=stat.st_size;start,end=0,size-1
        value=self.headers.get('Range')
        if value:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
            try:
                if not match or not any(match.groups()):raise ValueError()
                left,right=match.groups()
                if left:
                    start=int(left);end=min(int(right),size-1) if right else size-1
                else:
                    length=int(right)
                    if length<=0:raise ValueError()
                    start=max(0,size-length)
                if start>=size or start>end:raise ValueError()
            except ValueError:
                f.close();self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return None
            self.byte_range=(start,end)
        self.send_response(206 if self.byte_range else 200)
        self.send_header('Content-Type',self.guess_type(path));self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1));self.send_header('Last-Modified',self.date_time_string(stat.st_mtime))
        if self.byte_range:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers();return f
    def copyfile(self,source,output):
        try:
            if not self.byte_range:return super().copyfile(source,output)
            start,end=self.byte_range;source.seek(start);remaining=end-start+1
            while remaining:
                chunk=source.read(min(65536,remaining))
                if not chunk:break
                output.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=59137);p.add_argument('--directory',type=Path,default=Path(__file__).resolve().parent.parent);a=p.parse_args()
    http.server.ThreadingHTTPServer(('127.0.0.1',a.port),functools.partial(Handler,directory=str(a.directory.resolve()))).serve_forever()
if __name__=='__main__':main()
