#!/usr/bin/env python3
"""Minimal loopback-only Minecraft QA client. No gameplay automation or remote target support."""
from __future__ import annotations
import argparse, hashlib, json, socket, struct, threading, time, uuid, zlib
from pathlib import Path


def vi(value: int) -> bytes:
    value &= 0xffffffff
    result=bytearray()
    while True:
        b=value & 0x7f; value >>=7
        result.append(b | (0x80 if value else 0))
        if not value:return bytes(result)


def read_vi(data: bytes, offset=0):
    value=0
    for i in range(5):
        if offset+i>=len(data):raise ValueError('truncated VarInt')
        b=data[offset+i];value |= (b & 0x7f)<<(i*7)
        if not b & 0x80:return value,offset+i+1
    raise ValueError('oversized VarInt')


def text(value: str) -> bytes:
    encoded=value.encode('utf-8');return vi(len(encoded))+encoded


class Client:
    def __init__(self, port: int, play_keepalive: int, play_position: int, play_keepalive_reply: int,
                 username='NLWaterQA', protocol=776):
        self.sock=socket.create_connection(('127.0.0.1',port),timeout=20)
        self.sock.settimeout(2)
        self.events=[];self.stage='login';self.compression=None;self.closed=False
        self.keepalive=play_keepalive;self.position=play_position;self.keepalive_reply=play_keepalive_reply
        self.send(0,vi(protocol)+text('127.0.0.1')+struct.pack('>H',port)+vi(2))
        digest=bytearray(hashlib.md5(('OfflinePlayer:'+username).encode()).digest())
        digest[6]=(digest[6]&15)|48;digest[8]=(digest[8]&63)|128
        self.send(0,text(username)+digest)
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()

    def send(self, kind, payload=b''):
        packet=vi(kind)+payload
        if self.compression is not None:
            packet=(vi(len(packet))+zlib.compress(packet)) if len(packet)>=self.compression else b'\0'+packet
        self.sock.sendall(vi(len(packet))+packet)

    def exact(self,n):
        data=bytearray()
        while len(data)<n:
            try:part=self.sock.recv(n-len(data))
            except socket.timeout:
                if self.closed:raise EOFError('client stopped')
                continue
            if not part:raise EOFError('server closed connection')
            data.extend(part)
        return bytes(data)

    def packet(self):
        prefix=bytearray()
        for _ in range(5):
            prefix.extend(self.exact(1))
            if not prefix[-1]&128:break
        size,_=read_vi(prefix)
        if size>64*1024*1024:raise ValueError('packet exceeds QA bound')
        body=self.exact(size)
        if self.compression is not None:
            length,offset=read_vi(body);body=body[offset:]
            if length:body=zlib.decompress(body)
        kind,offset=read_vi(body);return kind,body[offset:]

    def loop(self):
        try:
            while not self.closed:
                try:kind,data=self.packet()
                except socket.timeout:continue
                if self.stage=='login':
                    self.events.append({'stage':self.stage,'packet':kind,'bytes':len(data)})
                    if kind==3:self.compression=read_vi(data)[0]
                    elif kind==2:
                        self.send(3);self.stage='configuration'
                    elif kind==0:raise RuntimeError('login rejected: '+data[:1000].hex())
                    elif kind==1:raise RuntimeError('QA requires the isolated offline-mode fixture')
                elif self.stage=='configuration':
                    self.events.append({'stage':self.stage,'packet':kind,'bytes':len(data)})
                    if kind==14:self.send(7,vi(0))
                    elif kind==4:self.send(4,data)
                    elif kind==5:self.send(5,data)
                    elif kind==3:
                        self.send(3);self.stage='play';self.send(44);self.events.append({'stage':'play','event':'configuration_completed'})
                    elif kind==2:raise RuntimeError('configuration disconnect: '+data[:1000].hex())
                else:
                    if kind==self.keepalive:self.send(self.keepalive_reply,data)
                    elif kind==12:self.send(11,struct.pack('>f',10.0))
                    elif kind==self.position:
                        teleport,_=read_vi(data);self.send(0,vi(teleport))
                        self.events.append({'stage':'play','event':'teleport_confirmed','id':teleport})
        except Exception as error:
            if not self.closed:self.events.append({'error':repr(error),'stage':self.stage})

    def close(self):
        self.closed=True
        try:self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        self.sock.close();self.thread.join(timeout=3)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=25595)
    p.add_argument('--keepalive',type=int,required=True)
    p.add_argument('--position',type=int,required=True)
    p.add_argument('--keepalive-reply',type=int,required=True)
    p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();client=Client(a.port,a.keepalive,a.position,a.keepalive_reply)
    try:time.sleep(a.seconds)
    finally:client.close();a.output.write_text(json.dumps(client.events,indent=2)+'\n')
if __name__=='__main__':main()
