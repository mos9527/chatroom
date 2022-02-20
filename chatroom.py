from asyncore import read
from datetime import datetime
from http import HTTPStatus
import json
from os.path import isfile
from pprint import pprint
from threading import Thread
from typing import List   
from urllib.parse import parse_qs
from shutil import copyfile
from pywebhost import PyWebHost, Request, VerbRestrictionWrapper, WriteContentToRequest
from pywebhost.modules import JSONMessageWrapper, ReadContentToBuffer, BinaryMessageWrapper
from pywebhost.modules.session import Session, SessionWrapper
from pywebhost.modules.websocket import WebsocketSession, WebsocketSessionWrapper

import coloredlogs,os,pywebhost,mimetypes,time,http,logging,base64,sys
coloredlogs.DEFAULT_LOG_FORMAT='%(hostname)s [%(name)s] %(asctime)s - %(message)s'
coloredlogs.install(20)
# For coloring logs
port = int(sys.argv[-1]) if len(sys.argv) == 2 else 3300
server = PyWebHost(('', port))
TEMP_PATH = 'temp'
def time_string():
    return datetime.now().strftime('%m-%d %H:%M:%S')
if not os.path.exists(TEMP_PATH):os.makedirs(TEMP_PATH)
# Clearing temp
for f in os.listdir(TEMP_PATH):
    fullpath = os.path.join(TEMP_PATH,f)
    if os.path.isfile(fullpath):
        logging.warning('Removing temp file %s' % f)
        try:
            os.remove(fullpath)            
        except IOError:
            logging.error('Cannot remove file %s' % f)
class File():
    def __init__(self,temp_file_path,file_size,file_name,file_type,object_type,file_key='') -> None:
        self.temp_file_path = temp_file_path
        self.file_size,self.file_name = int(file_size),file_name
        self.file_type,self.object_type = file_type,object_type
        self.bytes_read,self.bytes_written = 0,0        
        self.file_key=file_key
        self.ready = False
        self.stream = open(self.temp_file_path,'wb+')
        self.downloader = set()        
    def write(self,chunk):        
        self.bytes_written += self.stream.write(chunk)
        return self.bytes_written
    def read(self,size):
        chunk = self.stream.read(size)
        self.bytes_read += len(chunk)        
        return chunk
    def seek(self,*a,**k):return self.stream.seek(*a,**k)
    def dict(self) -> str:
        return {
            'key':self.file_key,
            'size':self.file_size,
            'name':self.file_name,
            'bytes_read':self.bytes_read,
            'bytes_written':self.bytes_written,
            'file_type':self.file_type,
            'object_type':self.object_type,
            'ready':self.ready,
            'downloader':list(self.downloader)
        }
    def __repr__(self) -> str:
        return '<File %s Size=%s Name=%s Path=%s DL=%s>' % (
            'Ready' if self.ready else 'Pending',
            self.file_size,
            self.file_name,
            self.temp_file_path,
            ', '.join(self.downloader)
        )
    downloader : set

boardcasts = [{'sender': 'server','type':'startup','time': time_string()}]
files = {}
def reset_boardcast(by=None,note=None,refresh_all=True):
    global boardcasts
    boardcasts = [
        boardcasts[0],  # server startup line
        {'sender': 'server', 'msg': '<warning>%s Erased the chat %s</warning>' % (
            by, ': <pre>%s<pre/>' % note if note else 'and left without a word.')}
    ]
    for ws in server.websockets:ws.send(ChatSession.rmt_msg(type='refresh'))
    return True
class ChatSession(WebsocketSession):
    logger = logging.getLogger('ChatSession')
    @staticmethod
    def msg(sender,**kwargs):
        return {'sender':sender,'time': time_string(),**kwargs}

    @staticmethod
    def rmt_msg(**kwargs):
        return ChatSession.msg('remote',**kwargs)
    @staticmethod
    def srv_msg(**kwargs):
        return ChatSession.msg('server',**kwargs)
    def cln_msg(self,msg):
        return ChatSession.msg(self.name,msg=msg if self.unblock_state else '<pre>%s</pre>' % msg.replace('<','&lt;').replace('>', '&gt;'))        

    def send_srv_msg(self,**kwargs):
        self.send(ChatSession.srv_msg(**kwargs))

    @property
    def ip(self): return f'{self.request.client_address[0]}:{self.request.client_address[1]}'

    @property
    def name(self):
        if not 'name' in self.keys():
            # setting default name
            device = self.request.useragent_string
            device = device.split('(')[1].split(')')[0]
            self.name = '%s %s' % (device,self.ip)
        return self['name']
    @name.setter
    def name(self, newname):
        self['name'] = newname
        self.set_session()

    @property
    def unblock_state(self):
        if not 'unblock_state' in self.keys():
            self.unblock_state = False # not unblocked
        return self['unblock_state']
    @unblock_state.setter
    def unblock_state(self, newstate):
        self['unblock_state'] = newstate

    @property
    def sess_users(self):
        return [sess['name'] for key, sess in pywebhost.modules.session._sessions.items() if 'name' in sess.keys()]
    
    @property
    def online_users(self):
        return [sess['name'] for sess in self.request.server.websockets if 'name' in sess.keys()]


    username_blacklist = {'server', 'remote', 'The Alpine'}
    def im(self, name):
        if name in ChatSession.username_blacklist:
            self.send_srv_msg(msg='<error>Invalid username %s - Username was rerserved</error>' % name)
        elif name in self.sess_users:
            self.send_srv_msg(msg='<error>Invalid username %s - Username was taken</error>' % name)
        else:
            self.name = name
            self.send_srv_msg(msg='<sucess>Changed username to %s</success>' % name)
            self.send_srv_msg(type='login',msg=self.name)            
        return True

    def toggle_unblock(self, opt=None):
        self.unblock_state = not self.unblock_state
        self.send_srv_msg(msg='<success>Turned %s HTML Tags</success>' % ['on','off'][not self.unblock_state])        
        return True

    def users(self, opt=None):
        self.send_srv_msg(type='users', msg=self.online_users)
        return True

    @staticmethod
    def erase(self, note):
        reset_boardcast(by=self.name,note=note)

    def end(self,opt):
        return self.close() or True

    command_whitelist = {
        'im': 'Rename yourself',
        # 'unblock': 'Enable/Disable HTML Tags parsing',
        # 'erase': 'Erase the chat log',
        'users':'Show other online users',    
        'end':'Disconnect from the server'
    }
    def onCommand(self, command):
        for c in range(0, 15):
            if c + 1 > len(command):
                return False
            if command[c] == '!':
                command = command[c + 1:].split(' ')
                if len(command) < 1:
                    return False
                if len(command) > 1:
                    command, content = command[0], ' '.join(command[1:])
                else:
                    command, content = command[0], None
                if not command in list(ChatSession.command_whitelist.keys()):
                    return False
                return getattr(self, command)(content)

    def onOpen(self,request : Request=None,content=None):
        global boardcasts
        if not self.session_id: self.set_session_id(path='/')
        if self.get('banned-until',None) and self.get('banned-until') > time.time():
            self.send_srv_msg(msg='<error>You\'re still banned from this server : %s (for %ss)</error>' % (
                self.get('banned-reason','(no reason given)'),
                int(self.get('banned-until') - time.time())
            ))
            return self.close()
        for b in boardcasts:
            self.send(b)
        self.send_srv_msg(type='login',msg=self.name)
        self.send_srv_msg(type='announce', msg=['<b>Help: </b><code>!%s</code>: %s' % item for item in self.command_whitelist.items()])                
        self.users()
        self['UA'] = self.request.useragent_string
        self['IP'] = self.ip
        self['ID'] = self.session_id
        self['online'] = True        
        self.logger.info('%s : Connected via %s' % (self,self.request.useragent_string))
                
    def onReceive(self, frame: bytearray):    
        message = frame.decode()
        if message and not self.onCommand(message):
            self.logger.info('%s : %s' % (self.name,message))
            boardcast(self.cln_msg(message))

    def onClose(self, request=None, content=None):
        if (request): return
        self['online'] = False        
        return super().onClose(request, content)
    
    def __repr__(self) -> str:
        return '<ChatSession IP=%s SessionId=%s Name=%s>' % (self.ip,self.session_id,self.name)

def get_active_connections() -> List[ChatSession]:
    return getattr(server,'websockets',[])

def get_sessions() -> List[dict]:
    return ChatSession._sessions.values()

def get_connection_by_id(sid) -> ChatSession:
    for conn in get_active_connections():
        if sid == conn.session_id : return conn

def boardcast(message):
    global boardcasts
    boardcasts.append(message)
    for ws in get_active_connections():
        ws.send(message)

@server.route('/.*')
def _index_static(initator,request: Request, content):
    real = 'html' + request.path
    if os.path.isfile(real):
        WriteContentToRequest(request, real,mime_type=mimetypes.guess_type(real)[0])
    else:
        # request.send_error(404)
        request.send_response(404)
        request.send_header('Content-Length', 0)
        request.end_headers()

class FileSession(Session):
    logger = logging.getLogger('File')
    def onCreate(self, request: Request, content):
        if not self.session_id: self.set_session_id(path='/')
        request.send_response(200)
        request.send_header('Access-Control-Allow-Origin','*')
    
    @VerbRestrictionWrapper(['POST'])
    @BinaryMessageWrapper(read=False)
    def _file_upload(self,request: Request, content):
        global files

        if not self.request.headers.get('Content-Length'):
            return self.request.send_error(http.HTTPStatus.BAD_REQUEST,'Content-Length unknown')
        if not self.request.headers.get('Content-Disposition'):
            return self.request.send_error(http.HTTPStatus.BAD_REQUEST,'Missing Content-Disposition header')

        length,disposition = self.request.headers['Content-Length'],self.request.headers['Content-Disposition']
        file_type,object_type = self.request.headers.get('Content-Type') or 'text/plain',self.request.headers.get('X-Object-Type') or 'file'
        disposition = parse_qs(disposition)
        filename = disposition['filename'][0]
        file_key = self.new_uid
        file = File(os.path.join(TEMP_PATH,file_key),length,filename,file_type,object_type,file_key)
        self.logger.info((self.get('name') or self.session_id) + ' : Uploading ' + filename + ' -> ' + file.temp_file_path)
        boardcast(ChatSession.msg(sender=self.get('name') or self.session_id ,type=object_type,msg=file_key))
        files[file_key] = file
        # save it locally
        ReadContentToBuffer(self.request,file)
        # end of our session        
        file.stream.flush()
        file.ready=True        
        return file_key
    @VerbRestrictionWrapper(['GET'])
    @JSONMessageWrapper(read=False)
    def _file_view(self,request: Request, content):        
        key = request.query['key'][0]        
        if not key in files.keys():
            return request.send_error(HTTPStatus.NOT_FOUND,'Resource not found')
        return files[key].dict()
    temp_img_path_format = '%s_thumb'
    temp_img_default = base64.b64decode('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')
    @VerbRestrictionWrapper(['GET'])    
    def _file_get(self,request: Request, content):
        key = request.query['key'][0]             
        if not key in files.keys():
            return request.send_error(HTTPStatus.NOT_FOUND,'Resource not found')
        file : File = files[key]
        self_name = self.get('name')
        self.logger.info((self_name or self.request.useragent_string) + '??' + ' : Downloading '  + file.file_name)
        file.downloader.add(self_name)
        while not file.bytes_written >= file.file_size:
            time.sleep(0.1) # wait till upload finishes        
        request.send_response(200)
        request.send_header('Content-Disposition','filename="%s"' % file.file_name)        
        if 'thumb' in request.query:
            # fetching thumbnails for images
            from PIL import Image
            temp_img_path = FileSession.temp_img_path_format % file.temp_file_path
            if not isfile(temp_img_path):
                # creating one if object does not exist
                try:                    
                    thumb : Image.Image = Image.open(file.temp_file_path)
                    thumb.thumbnail((128,128))
                    thumb.save(temp_img_path,"JPEG")                    
                except:
                    # failed to parse
                    return WriteContentToRequest(request,file.temp_file_path,partial_acknowledge=True,mime_type=file.file_type)
            return WriteContentToRequest(request,temp_img_path,mime_type='image/jpg')
            # writing temp image
        else:
            if not self_name in file.downloader:
                # boardcast download event
                boardcast(ChatSession.srv_msg(msg={'file':file.dict(),'user':self_name},type='filedownload'))
            return WriteContentToRequest(request,file.temp_file_path,partial_acknowledge=True,mime_type=file.file_type)
    
@server.route('/ws')
@WebsocketSessionWrapper()
def _websocket(initator,request: Request, content):
    return ChatSession    

@server.route('/file/.*')
@SessionWrapper()
def _file(initator,request: Request, content):
    return FileSession

@server.route('/')
def _index(initator,request: Request, content):
    # Indexes folders of local path and 'renders' a webpage    
    WriteContentToRequest(request, 'html/chatroom.html', mime_type='text/html')

if __name__ == '__main__':        
    def _serve():
        logging.info(f'- Serving...http://127.0.0.1:{port} {server.protocol_version}')
        logging.warning('! Cookies will NOT work on localhost (RFC2109)')
        server.serve_forever()
    tServer = Thread(target=_serve,name='Server',daemon=True)
    tServer.start()            
    print('* Chatroom CLI Management Console *')
    print('* Note : This help message will only be shown ONCE!\n')
    # User Management
    def lsu(filter=None):
        count = 0
        for session in filter or get_sessions():
            print('[%s]' % session['ID'],','.join(['%s=%s' % (k,v) for k,v in session.items()]))
            count += 1
        print('- Total %s' % count)
    print('''- USER MANAGEMENT
        lsusr(user-filter) : List currently online users
    ''')
    # Filters
    def by_name(name,src=None):
        return filter(lambda i:name in i['name'],src or get_sessions())
    def by_ip(ip,src=None):
        return filter(lambda i:ip == i['IP'],src or get_sessions())
    def by_id(sid,src=None):
        return filter(lambda i:sid in i['ID'],src or get_sessions())        
    def online(src=None):
        return filter(lambda i:i['online'],src or get_sessions())        
    print('''-- USER FILTERS
        * Filters that applies to all sessions
        * Filters can be chained. e.g. by_name('11',online())
        by_name(username,...) : Pick users by username (if contain)        
        by_id(id,...) : Pick users by id (if contain)
        by_ip(ip,...) : Pick user by ip
        online(...) : All online users
    ''')
    def unblock(filter):    
        for session in filter:
            connection = get_connection_by_id(session['ID'])
            connection.toggle_unblock()
            print('! HTML Parsing for %s : %s' % (session.name,session.unblock_state))
    def kick(filter,reason=''):
        for session in filter:
            connection = get_connection_by_id(session['ID'])
            connection.send_srv_msg(msg="You are kicked from the server : %s" % (reason or '(no reason given)'))
            connection.close()
            print('! Kicked',session)
    def ban(filter,duration=30,reason=''):    
        for session in filter:
            connection = get_connection_by_id(session['ID'])
            connection.send_srv_msg(msg="You are banned from the server : %s" % (reason or '(no reason given)'))
            session['banned-reason'] = reason
            session['banned-until'] = time.time() + int(duration)
            connection.close()
            print('! Banned',session,'for %ss' % duration) 
    def rename(filter,name_to=''):
        for session in filter:
            session.name = name_to
            connection = get_connection_by_id(session['ID'])
            connection.send_srv_msg(msg="You are now : %s" % name_to)                        
    print('''-- USER OPs
        * Selections are made by User Filters (see above)
        unblock(user-filter) : Allow selected users to send raw HTML
        kick(user-filter,reason) : Kicks selected users
        ban(user-filter,duration=30,reason) : Ban selected users (set duration belown 0 to unban them!)
        rename(user-filter,name_to) : Rename user
    ''')
    # File Management
    print('''- FILE MANAGEMENT
    * Files are tempoarly stored in "%s"
        ls(file-filter) : List currently stored files
    ''' % TEMP_PATH)
    def ls(filter=None):
        count = 0
        for key,file in filter or files.values():
            print(key,file)
            count += 1
        print('Total %s' % count)
    print('''-- FILE FITLERS
        * Operates like user filters
        by_file_name(filename,...) : Pick files by username (if contain)
        by_file_name(id,...) : Pick files by id (if contain)    
    ''')
    # Filters
    def by_file_name(name,src=None):
        return filter(lambda i:name in i.file_name,src or files.values())
    def by_file_id(id,src=None):
        return filter(lambda i:id in i.file_key,src or files.values())
    print('''-- FILE OPs
    * Selections are made by File Filters (see above)
        export(file-filter,to='.') : Save selected files to a certain location with their original filenames
    ''')
    def export(filter,to='.'):
        print('= Currently held files')
        for file in filter:
            file : File
            to = os.path.join(to,file.file_name)
            print('Copying %s -> %s' % (file.temp_file_path,file.file_name))
            copyfile(file.temp_file_path,to)    
    # Misc
    def say(msg):
        return boardcast(ChatSession.msg(sender='The Alpine',msg=msg))
    def logs():
        pprint(boardcasts,indent=4)
    def erase(note=''):
        reset_boardcast(by='The Alpine',note=note)
    def save(to='chat.json'):
        return open(to,encoding='utf-8',mode='w').write(json.dumps(boardcasts,ensure_ascii=False,indent=4))
    def load(frm='chat.json'):
        global boardcasts
        boardcasts = json.loads(open(frm,encoding='utf-8').read())
    print('''- MISC OPs
        say(message) : Say something as The Alpine
        logs() : View current full chat log
        erase(note) : Clear current chat log, and leave a message
        save(path) : Save current log to file
        load(path) : Load log from file to restore chats
    ''')
    # The main thread spawns an interactive terminal for more administrative operations
    from code import interact
    interact(banner='* Console is now ready (Press Ctrl+D to exit).',local=locals())