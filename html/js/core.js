const HEARTBEAT_INTERVAL = 10000, MARQUEE_INTERVAL = 2000
var wsURI = window.location.protocol.replace('http', 'ws') + '//' + window.location.hostname + (window.location.port ? ':' + window.location.port : '') + window.location.pathname + 'ws'
var server, username, announcements = []
function U_hrs(size) {
    var i = Math.floor(Math.log(size) / Math.log(1024))
    return size ? (size / Math.pow(1024, i)).toFixed(2) * 1 + ' ' + ['B', 'kB', 'MB', 'GB', 'TB'][i] : '0 B'
}


function T_user(user,level){
    return `<span class="badge badge-${level || 'info'}" style="margin-left:5px">${user}</span>`
}

function T_file(file) {    
    const fileImgs = {
        image:'fas fa-file-image',
        video:'fas fa-file-video',
        default:'fas fa-file-alt'
    }
    var fileImg = fileImgs[file.file_type.split('/')[0]] || fileImgs['default']
    fileImg = fileImg     
    var str = `<div class="media"><i class="${fileImg} mr-3 file-icon"></i><div class="media-body">`
    str += `<h5 class="mt-0">${file.name}</h5>`
    str += `<p class="mb-1">${U_hrs(file.size)} - ${file.file_type}</p>`
    str += '</div></div><div class="progress">'
    str += `<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar">用户上传中</div></div>`
    return str
}

function T_image(src) {
    return `<img class="rounded float-left img-fluid" src="${src}"></img><div class="spinner-grow" role="status"></div>`
}

function T_announce(message) {
    return `${message}`
}
function T_alert_error(message, level) {
    const icons = { danger: 'exclamation-circle', warning: 'exclamation-triangle', primary: 'check' }
    icon = icons[level] || 'check'
    var str = `<div class="alert alert-${level}" role="alert">`
    str += `<i class="fa fa-${icon} mr-2"></i>${message}</div>`
    return str
}

function T_chat(heading, content, footer) {    
    var str = '<div class="card chat">'
    str += '<div class="d-flex w-100 justify-content-between">'
    str += `<sender class="mb-1">${heading}</sender>`
    str += `<small class="text-muted">${footer}</small></div>`
    str += `<p class="mb-1">${content}</p></div>`
    return str
}

function T_chat_alt(heading, content, footer) {
    var str = '<div class="card chat">'
    str += '<div class="d-flex w-100 justify-content-between">'
    str += `<sender class="mb-1">${heading}</sender>`
    str += `<small class="text-muted">${footer}</small></div>`
    str += `<p class="mb-1">${content}</p></div>`
    return str
}
function Prepend(message){
    $('#chats').prepend(message)
    setTimeout(()=>{
        message.addClass('chat-shown')
    },0)
}

function Alert(message, level) {
    $('.toast-header').after(
        T_alert_error(message, level || 'primary')
    )
    $('.alert').click(function () {
        $(this).addClass('out')
        setTimeout(() => { $(this).remove() }, 500)
    })
}

function connect() {
    return new Promise(function (resolve, reject) {
        var ws = new WebSocket(wsURI)
        ws.onopen = () => resolve(ws)
        ws.onerror = err => reject(err)
    })
}

function onServerMessage(e) {
    var content = JSON.parse(e.data)
    var sender_router = {
        server: () => {
            /* Server side messages */
            var type_router = {
                startup: () => {
                    server.startup = connect.time
                },
                login: () => {
                    username = content.msg
                },
                announce: () => {
                    for (var msg of content.msg) announcements.push(msg)                    
                    nextAnnouce()
                },
                users: () => {
                    var users='';
                    content.msg.filter(user => {users += T_user(user,user == username ? 'primary' : 'info');return true;})
                    Alert('Users: ' + users)
                },
                undefined: () => {
                    // For normal server messages 
                    Alert(content.msg, 'warning')
                }
            }
            var action = type_router[content.type]
            action = action || type_router[action]
            action()
        },
        remote: () => {
            /* Server side RCE */
            var type_router = {
                refresh: () => {
                    location.reload()
                },
                undefined: () => {
                    // router shouldn't go here
                }
            }
            var action = type_router[content.type]
            action = action || type_router[action]
            action()
        },
        undefined: () => {
            /* Messages by other users */
            var type_router = {
                refresh: () => {
                    location.reload()
                },
                file: () => {
                    // Only files' IDs are being sent                    
                    var chat = $(T_chat(content.sender, 'Loading...', content.time))
                    // creates empty placeholder
                    Prepend(chat)
                    fetch('file/view?key=' + content.msg, {
                        method: 'GET'
                    }).then(response => response.json()).then(file => {
                        function update(file) {
                            var bar = $(chat).find('.progress-bar')
                            var rate = file.bytes_written - bar.attr('aria-valuenow') || 0;
                            bar.attr('aria-valuenow',file.bytes_written)
                            bar.attr('aria-valuemax',file.bytes_written)
                            bar.css('width', file.bytes_written / file.size * 100 + '%')                                                        
                            bar.text(`Uploading: ${U_hrs(rate)} / s`)
                            if (!file.ready) {
                                setTimeout(fetch_, 1000); // fetch as long as the transmission isn't over
                            } else {
                                if (file.bytes_written >= file.size) {                                    
                                    $(chat).find('.progress-bar').html(
                                        '<button class="btn-secondary"' +
                                        `onclick="window.open('file/get?key=${file.key}')"><a class="text-light" href="file/get?key=${file.key}">DOWNLOAD</a></button>`
                                    )
                                } else {
                                    $(chat).find('.progress-bar').addClass('bg-danger').text('Upload was canceled')
                                }
                            }
                        }
                        function fetch_() {
                            fetch('file/view?key=' + content.msg, {
                                method: 'GET'
                            }).then(response => response.json()).then((file) => update(file))
                        }
                        $(chat).find('p.mb-1').html(T_file(file))
                        update(file)
                    }).catch((err) => {
                        console.error('While fetching file info...' + err)
                    })
                },
                image: () => {
                    var url = 'file/get?key=' + content.msg
                    var image = T_image(url)
                    var chat = $(T_chat(content.sender, image, content.time))
                    chat.find('img').on('load', function () { chat.find('.spinner-grow').remove() })
                    Prepend(chat)
                },
                undefined: () => {
                    // For normal user messages
                    var chat = $(T_chat(content.sender, content.msg, content.time))
                    Prepend(chat)
                }
            }
            var action = type_router[content.type]
            action = action || type_router[action]
            action()
            $('audio')[0].play() // play notification sound for user messages
        }
    }
    var action = sender_router[content.sender]
    action = action || sender_router[action]
    action()    
}

function sendMessage() {
    /* Sending message */
    server.send($('#messagePlane').val())
    $('#messagePlane').val('')
}
$('#messageButton').click(sendMessage)
$('#messagePlane').keydown((e) => { if (e.ctrlKey && e.key == "Enter") sendMessage() })
// Message send triggers
function nextAnnouce() {
    msg = announcements.shift()        
    if(!msg)return
    announcements.push(msg)
    $('#announce').fadeOut(()=>{
        $('#announce').html(T_announce(msg))
        .fadeIn().find('code').on('click',function(){
            // for <code>,treat them as litte snippets which can be then added
            // to our input
            $('#messagePlane').val($(this).text())
            $('#messageInput').collapse('show')
        }).css('cursor','pointer')
    })
}
setInterval(nextAnnouce, MARQUEE_INTERVAL)
setInterval(function heartBeat() {
    server.send('')
}, HEARTBEAT_INTERVAL)
// Annouce scroller
function upload(files) {
    for (file of files) {
        var uploadType = $('#file').attr('upload-type')
        uploadType = uploadType == 'auto' ? (file.type.search('image') ? 'image' : file) : uploadType
        if (uploadType == 'image' && file.type.search('image')==-1) return; // trying to upload non-image file to file type
        fetch('file/upload', {
            method: 'POST',
            headers: {
                'X-Object-Type': uploadType,
                'Content-Type': file.type,
                'Content-Length': file.size,
                'Content-Disposition': 'filename=' + encodeURIComponent(file.name)
            },
            body: file
        }).then((response) => {
            // Alert('上传成功')
        }).catch((err) => {
            Alert(`Exception while uploading:${err}`, 'danger')
        })
    }
}
$('.click-uploader-img').on('click', () => { $('#file').attr('upload-type','image'); $('#file').click() })
$('.click-uploader-file').on('click', () => { $('#file').attr('upload-type','file'); $('#file').click() })
$('#file').on('change', function () { upload(this.files) })
// Upload functions
connect().then((ws) => {
    server = ws
    server.onmessage = onServerMessage
    server.onclose = (e) => {
        Alert('Disconnected: ' + e.code, 'danger')
        announcements = ['DISCONNECTED']
    }
}).catch((err) => {
    Alert(err)
})