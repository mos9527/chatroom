from datetime import datetime
from http import HTTPStatus
import http
import logging
from logging import INFO, WARNING
from urllib.parse import parse_qs
from pywebhost import PyWebHost, Request, VerbRestrictionWrapper, WriteContentToRequest
from pywebhost.modules import JSONMessageWrapper, ReadContentToBuffer, BinaryMessageWrapper
from pywebhost.modules.session import Session, SessionWrapper
from pywebhost.modules.websocket import WebsocketSession, WebsocketSessionWrapper

import coloredlogs,os,pywebhost,mimetypes,time
coloredlogs.DEFAULT_LOG_FORMAT='%(hostname)s [%(name)s] %(asctime)s - %(message)s'
coloredlogs.install(WARNING)
# For coloring logs
port = 3300
server = PyWebHost(('', port))
TEMP_PATH = 'temp'
def time_string():
    return datetime.now().strftime('%m-%d %H:%M:%S')
if not os.path.exists(TEMP_PATH):os.makedirs(TEMP_PATH)
# Clearing temp
for f in os.listdir(TEMP_PATH):
    fullpath = os.path.join(TEMP_PATH,f)
    if os.path.isfile(fullpath):
        logging.info('Removing temp file %s' % f)
        try:
            # os.remove(fullpath)
            pass
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
            'ready':self.ready
        }

boardcasts = [{'sender': 'server','type':'startup',
               'time': time_string()}]

files = {}

def boardcast(message):
    global boardcasts
    boardcasts.append(message)
    for ws in server.websockets:
        ws.send(message)

class Chat(WebsocketSession):
    @staticmethod
    def msg(sender,**kwargs):
        return {'sender':sender,'time': time_string(),**kwargs}

    @staticmethod
    def rmt_msg(**kwargs):
        return Chat.msg('remote',**kwargs)
    @staticmethod
    def srv_msg(**kwargs):
        return Chat.msg('server',**kwargs)
    def cln_msg(self,msg):
        return Chat.msg(self.name,msg=msg if self.unblock_state else '<pre>%s</pre>' % msg.replace('<','&lt;').replace('>', '&gt;'))        

    def send_srv_msg(self,**kwargs):
        self.send(Chat.srv_msg(**kwargs))

    @property
    def ip(self): return f'{self.request.client_address[0]}:{self.request.client_address[1]}'

    @property
    def name(self):
        if not 'name' in self.keys():
            self.name = self.ip
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


    username_blacklist = {'server', 'remote'}
    def im(self, name):
        if name in Chat.username_blacklist:
            self.send_srv_msg(msg='<error>Invalid username %s - Username was rerserved</error>' % name)
        elif name in self.sess_users:
            self.send_srv_msg(msg='<error>Invalid username %s - Username was taken</error>' % name)
        else:
            self.name = name
            self.send_srv_msg(msg='<sucess>Changed username to %s</success>' % name)
            self.send_srv_msg(type='login',msg=self.name)            
        return True

    def unblock(self, opt=None):
        self.unblock_state = not self.unblock_state
        self.send_srv_msg(msg='<success>Turned %s HTML Tags</success>' % ['on','off'][not self.unblock_state])        
        return True

    def users(self, opt=None):
        self.send_srv_msg(type='users', msg=self.online_users)
        return True

    def erase(self, note):
        global boardcasts
        boardcasts = [
            boardcasts[0],  # server startup line
            {'sender': 'server', 'msg': '<warning>%s Cleared the chat : %s</warning>' % (
                self.name, note if note else '...')}
        ]
        for ws in self.request.server.websockets:ws.send(self.rmt_msg(type='refresh'))
        return True

    def end(self,opt):
        return self.close() or True

    command_whitelist = {
        'im': 'Rename yourself',
        'unblock': 'Enable/Disable HTML Tags parsing',
        'erase': 'Erase the chat',
        'users':'Show others online',    
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
                if not command in list(Chat.command_whitelist.keys()):
                    return False
                return getattr(self, command)(content)

    def onOpen(self):
        global boardcasts
        for b in boardcasts:
            self.send(b)
        self.send_srv_msg(type='login',msg=self.name)
        self.send_srv_msg(type='announce', msg=['<b>Help: </b><code>!%s</code>: %s' % item for item in self.command_whitelist.items()])                
        self.users()
        print('%s : Connected via %s' % (self.name,self.request.useragent_string()))
                
    def onReceive(self, frame: bytearray):    
        message = frame.decode()
        if message and not self.onCommand(message):
            print('%s : %s' % (self.name,message))
            boardcast(self.cln_msg(message))

@server.route('/.*')
def index(initator,request: Request, content):
    real = 'html' + request.path
    if os.path.isfile(real):
        WriteContentToRequest(request, real,mime_type=mimetypes.guess_type(real)[0])
    else:
        # request.send_error(404)
        request.send_response(404)
        request.send_header('Content-Length', 0)
        request.end_headers()

class FileSession(Session):

    def onOpen(self):
        self.request.send_response(200)
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
        print(self.get('name') or self.session_id , ': Uploading',filename,'->',file.temp_file_path)
        boardcast(Chat.msg(sender=self.get('name') or self.session_id ,type=object_type,msg=file_key))
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
    
    @VerbRestrictionWrapper(['GET'])
    @JSONMessageWrapper(read=False)
    def _file_get(self,request: Request, content):
        key = request.query['key'][0]             
        if not key in files.keys():
            return request.send_error(HTTPStatus.NOT_FOUND,'Resource not found')
        file : File = files[key]
        print(self.get('name') or self.request.useragent_string() + ' -- Anonymous --',': Downloading',file.file_name)   
        while not file.bytes_written >= file.file_size:
            time.sleep(0.1) # wait till upload finishes        
        request.send_response(200)
        request.send_header('Content-Disposition','filename="%s"' % file.file_name)
        WriteContentToRequest(request,open(file.temp_file_path,'rb'),True,file.file_size,mime_type=file.file_type)
    
@server.route('/ws')
@WebsocketSessionWrapper()
def websocket(initator,request: Request, content):
    return Chat
    # Starts serving and blocks the current thread

@server.route('/file/.*')
@SessionWrapper()
def file(initator,request: Request, content):
    # if not request.cookies[SESSION_KEY]:
    #     request.send_error(http.HTTPStatus.FORBIDDEN,'Request not authorized')
    # else:
    return FileSession

@server.route('/')
def index(initator,request: Request, content):
    # Indexes folders of local path and renders a webpage
    WriteContentToRequest(request, 'html/chatroom.html', mime_type='text/html')

print(f'Serving...http://localhost:{port} {server.protocol_version}')
server.serve_forever()
