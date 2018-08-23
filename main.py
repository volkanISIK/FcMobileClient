import socket
import struct
import threading
import time
import select
import kivy
import random
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.lang import Builder
from kivy.config import Config
from kivy.uix.scrollview import ScrollView
from kivy.properties import StringProperty
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition, ObjectProperty
from kivy.clock import Clock
import threading


Builder.load_file("fightcadekivy.kv")
COLORS = ["6adfe8","7ce829","fcf016","fc1414","2833ff","8223ff","ff688b","68ff93","00ffff","f8a300","a0333a","b83347","004d33","007256","16216a","0065b1","ffc000","00a43b","613339","bb3016","6e4a75","ff2300"]
class PlayerStates:
    AVAILABLE = 0x0
    AFK = 0x1
    PLAYING = 0x2
    QUIT = 0xff  # my own, not GGPO server's

    @staticmethod
    def codeToString(code):
        if code == 0:
            return 'AVAILABLE'
        elif code == 1:
            return 'AFK'
        elif code == 2:
            return 'PLAYING'
        elif code == 0xff:
            return 'QUIT'
        else:
            return 'Unknown (' + hex(code) + ')'
class Protocol:
    # IN BAND
    WELCOME = 0x0
    AUTH = 0x1
    MOTD = 0x2
    LIST_CHANNELS = 0x3
    LIST_USERS = 0x4
    JOIN_CHANNEL = 0x5
    TOGGLE_AFK = 0x6
    CHAT = 0x7
    SEND_CHALLENGE = 0x8
    ACCEPT_CHALLENGE = 0x9
    DECLINE_CHALLENGE = 0xa
    SPECTATE = 0x10
    CANCEL_CHALLENGE = 0x1c
    # OUT OF BAND
    CHALLENGE_RETRACTED = 0xffffffef
    SPECTATE_GRANTED = 0xfffffffa
    CHALLENGE_DECLINED = 0xfffffffb
    CHALLENGE_RECEIVED = 0xfffffffc
    PLAYER_STATE_CHANGE = 0xfffffffd
    CHAT_DATA = 0xfffffffe
    JOINING_A_CHANNEL = 0xffffffff

    AllReverseMap = {
        0x0: 'WELCOME',
        0x1: 'AUTH',
        0x2: 'MOTD',
        0x3: 'LIST_CHANNELS',
        0x4: 'LIST_USERS',
        0x5: 'JOIN_CHANNEL',
        0x6: 'TOGGLE_AFK',
        0x7: 'CHAT',
        0x8: 'SEND_CHALLENGE',
        0x9: 'ACCEPT_CHALLENGE',
        0xa: 'DECLINE_CHALLENGE',
        0x10: 'SPECTATE',
        0x1c: 'CANCEL_CHALLENGE',
        0xffffffef: 'CHALLENGE_RETRACTED',
        0xfffffffa: 'SPECTATE_GRANTED',
        0xfffffffb: 'CHALLENGE_DECLINED',
        0xfffffffc: 'CHALLENGE_RECEIVED',
        0xfffffffd: 'PLAYER_STATE_CHANGE',
        0xfffffffe: 'CHAT_DATA',
        0xffffffff: 'JOINING_A_CHANNEL',
    }

    OutOfBandReverseMap = {
        0xffffffef: 'CHALLENGE_RETRACTED',
        0xfffffffa: 'SPECTATE_GRANTED',
        0xfffffffb: 'CHALLENGE_DECLINED',
        0xfffffffc: 'CHALLENGE_RECEIVED',
        0xfffffffd: 'PLAYER_STATE_CHANGE',
        0xfffffffe: 'CHAT_DATA',
        0xffffffff: 'JOINING_A_CHANNEL',
    }

    @staticmethod
    def codeToString(code):
        if code in Protocol.AllReverseMap:
            return Protocol.AllReverseMap[code]
        return 'SEQ (' + hex(code) + ')'

    @staticmethod
    def outOfBandCodeToString(code):
        if code in Protocol.OutOfBandReverseMap:
            return Protocol.OutOfBandReverseMap[code]
        return 'SEQ (' + hex(code) + ')'

    @staticmethod
    def unpackInt(data):
        n=0
        try:
            n, = struct.unpack("!I", data)
        except:
            pass
        return n

    @staticmethod
    def packInt(n):
        return struct.pack("!I", n)

    @staticmethod
    def packTLV(data):
        return struct.pack("!I", len(data)) + data

    @staticmethod
    def extractTLV(data):
        """
        data is encoded in array of bytes in [length:value:rest] format
        extract and return the value and the rest of the bytes in a tuple
        @param data:
        @return: tuple(data, rest)
        """
        length = Protocol.unpackInt(data[:4])
        value = data[4:length + 4]
        return value, data[length + 4:]

    @staticmethod
    def extractInt(data):
        """
        data is encoded in array of bytes in [int32:rest] format
        extract and return the int32 and the rest of the bytes in a tuple
        @param data:
        @return: tuple(int, rest)
        """
        intval = Protocol.unpackInt(data[0:4])
        return intval, data[4:]
class Player:
    _ID = 0

    def __init__(self, **kwargs):
        self.id = self._ID
        self.__class__._ID += 1
        self.player = ''
        self.ip = ''
        self.port = 6009
        self.city = ''
        self.cc = ''
        self.country = ''
        self.ping = ''
        self.lastPingTime = 0
        self.loc = ''
        self.spectators = 0
        self.color= random.choice(COLORS)
        vars(self).update(kwargs)



class Scroll_Label(ScrollView):
    text = StringProperty("")
class LoginScreen(Screen):
    name = StringProperty("login_screen")
class Chat(Screen):
    name = StringProperty("chat_screen")



class FightcadeCilent(ScreenManager):

    (STATE_TCP_READ_LEN, STATE_TCP_READ_DATA) = range(2)

    state = StringProperty('set_main_menu_state')
    screen_manager = ObjectProperty(None)
    playerss = StringProperty("")
    chatLog = StringProperty("")
    message = StringProperty("")
    def __init__(self, **kwargs):
        super(FightcadeCilent, self).__init__(**kwargs)
        self.selectTimeout = 1
        self.players = {}
        self.available = {}
        self.playing = {}
        self.awayfromkb = {}
        self.tcpData = ''
        self.tcpReadState = self.STATE_TCP_READ_LEN
        self.tcpResponseLen = 0
        self.tcpCommandsWaitingForResponse = dict()
        self.tcpSock = None
        self.username = ""
        self.playingagainst = ""
        self.sequence = 0x1
        
       

    def set_state(self, state):
        if state == 'chat_screen':
            self.screen_manager.current = 'login_screen'
        if state == 'login_screen':
            self.screen_manager.current = 'chat_screen'

    def switch_to_chat_screen(self):
        self.screen_manager.current = 'chat_screen'
    def switch_to_login_screen(self):
        self.screen_manager.current = 'login_screen'
    def baglan(self,username,password):
        self.username = username
        self.password = password
        result = self.login(self.username,self.password)
        if result == 1:
            Clock.schedule_interval(self.connect_to_server,4)
            self.switch_to_chat_screen()
        elif result == 2:
            self.message = "heyy are you sure? incorrect username or password"
        elif result == 3:
            self.message = ":( sorry cannot connect to this fucking server :( "

    def connect_to_server(self,e):
        self.playerss = ""
        self.mainloop()

    def fillPlayers(self):
        playingSet = set()
        for x in self.available:
            self.playerss = self.playerss + "\n"+"[color={}]{}[/color]".format(self.players[x].color,x)
        for x in self.playing:
            playingSet.add(x)
            if self.playing[x] not in playingSet:
                if self.playing[x] in self.players:
                    self.playerss = self.playerss + "\n" + "[color={}]{}[/color] -vs- [color={}]{}[/color]".format(self.players[x].color,x,self.players[self.playing[x]].color,self.playing[x])
                else:
                    self.playerss = self.playerss + "\n" "[color={}]{}[/color] -vs- null".format(self.players[x].color,x)
        for x in self.awayfromkb:
            self.playerss = self.playerss + "\n" + "[color={}]{}[/color] (away)".format(self.players[x].color,x)
    def addChat(self,name,msg):
        self.chatLog = self.chatLog + "\n" + "[color={}]<{}>[/color] [color={}]{}[/color]".format(self.players[name].color,name,random.choice(COLORS),msg)
    def exit(self):
        Clock.unschedule(self.connect_to_server)
        try:
            self.tcpSock.close()
        except:
            pass
        self.switch_to_login_screen()
    def sendAndRemember(self,command, data=''):
        #global tcpCommandsWaitingForResponse,sequence
        #logdebug().info('Sending {} seq {} {}'.format(Protocol.codeToString(command), self.sequence, repr(data)))
        self.tcpCommandsWaitingForResponse[self.sequence] = command
        self.sendtcp(struct.pack('!I', command) + data)

    def sendtcp(self,msg):
        #global sequence
        # length of whole packet = length of sequence + length of msg
        payloadLen = 4 + len(msg)
        # noinspection PyBroadException
        try:
            self.tcpSock.send(struct.pack('!II', payloadLen, self.sequence) + str(msg))
        except:
            # print("tcp send gonderemedi")
            pass
        self.sequence += 1


    def sendAuth(self,username, password):
        # try:
        #     port = self.s.getsockname()[1]
        # except:
        #     port=6009
        #     #raise
        authdata = Protocol.packTLV(username) + Protocol.packTLV(password) + Protocol.packInt(6009) + Protocol.packInt(43)
        # print("auth data {} {} {} {}".format(username,password,6009,42))
        self.sendAndRemember(Protocol.AUTH, authdata)
    def sendToggleAFK(self, afk):
        if afk:
            val = 1
            state = True
        else:
            val = 0
            state = False
        self.sendAndRemember(Protocol.TOGGLE_AFK, Protocol.packInt(val))



    def sendChat(self,line):
            line = line.encode('utf-8')
            self.sendAndRemember(Protocol.CHAT,Protocol.packTLV(line))

    def parseChatResponse(self,data):
        name, data = Protocol.extractTLV(data)
        msg, data = Protocol.extractTLV(data)

        #msg = data.decode('utf-8')
        try:

            msg = unicode(msg, "utf-8")
            name = unicode(name, "utf-8")
            # print type(msg),type(name)
            msg = msg.decode("utf-8")
            name = name.decode("utf-8")
        except ValueError:
            msg = "dont use unicode charters mr.{}".format(name)

            # print("------------------unicode hatasi-----------------------")
        # print("<{}> {}".format(name,msg))
        self.addChat(name,msg)





    def parseMotdResponse(self, data):
            if not data:
                print("motd de data yok")
                return
            status, data = Protocol.extractInt(data)
            channel, data = Protocol.extractTLV(data)
            topic, data = Protocol.extractTLV(data)
            msg, data = Protocol.extractTLV(data)
            #print(" motd data == {} / {} / {} / {}".format(status,channel,topic,msg))

    def handleTcpResponse(self):
        #global tcpReadState,tcpData,tcpResponseLen
        # print "burasi calisti mi 6"
        if self.tcpReadState == self.STATE_TCP_READ_LEN:
            # print "burasi calisti mi 7"
            if len(self.tcpData) >= 4:
                # print "burasi calisti mi 7.1"
                self.tcpResponseLen, self.tcpData = Protocol.extractInt(self.tcpData)
                self.tcpReadState = self.STATE_TCP_READ_DATA
                self.handleTcpResponse()
        elif self.tcpReadState == self.STATE_TCP_READ_DATA:
            # print "burasi calisti mi 8"
            if len(self.tcpData) >= self.tcpResponseLen:
                # tcpResponseLen should be >=
                # print "burasi calisti mi 8.1"
                if self.tcpResponseLen < 4:
                    # print "burasi calisti mi 8.2"
                    self.tcpData = self.tcpData[self.tcpResponseLen:]
                    self.tcpResponseLen = 0
                    self.tcpReadState = self.STATE_TCP_READ_LEN
                    self.handleTcpResponse()
                else:
                    # print "burasi calisti mi 9"
                    data = self.tcpData[:self.tcpResponseLen]
                    self.tcpData = self.tcpData[self.tcpResponseLen:]
                    seq = Protocol.unpackInt(data[0:4])
                    self.tcpResponseLen = 0
                    self.tcpReadState = self.STATE_TCP_READ_LEN
                    self.dispatch2(seq, data[4:])
                    self.handleTcpResponse()
    def parseListUsersResponse(self, data):
        #global available,awayfromkb,playing
        self.resetPlayers()
        if not data:
            return
        status, data = Protocol.extractInt(data)
        status2, data = Protocol.extractInt(data)
        while len(data) > 8:
            p1, data = Protocol.extractTLV(data)
            # if len(data) <= 4: break
            state, data = Protocol.extractInt(data)
            p2, data = Protocol.extractTLV(data)
            ip, data = Protocol.extractTLV(data)
            unk1, data = Protocol.extractInt(data)
            unk2, data = Protocol.extractInt(data)
            city, data = Protocol.extractTLV(data)
            cc, data = Protocol.extractTLV(data)
            country, data = Protocol.extractTLV(data)
            port, data = Protocol.extractInt(data)
            spectators, data = Protocol.extractInt(data)
            self.addUser(
                player=p1,
                ip=ip,
                port=port,
                city=city,
                cc=cc,
                country=country,
                spectators=spectators+1,
            )
            if state == PlayerStates.AVAILABLE:
                self.available[p1] = True
            elif state == PlayerStates.AFK:
                self.awayfromkb[p1] = True
            elif state == PlayerStates.PLAYING:
                if not p2:
                    p2 = 'null'
                self.playing[p1] = p2
    def addUser(self, **kwargs):

        #global available,awayfromkb,playing,players
        # print ("buraya girdik mi (addUser())")
        if 'player' in kwargs:
            name = kwargs['player']
            if name not in self.available and name not in self.awayfromkb and name not in self.playing:
                pass
            if name in self.players:
                pass
                #p = self.players[name]
                # for k, v in kwargs.items():
                #     if v and not (k == 'cc' and isUnknownCountryCode(v)):
                #         setattr(p, k, v)
            else:
                p = Player(**kwargs)
                self.players[name] = p

    def resetPlayers(self):
        #global available,playing,awayfromkb
        # print("buraya girdik mi hic resetPlayers(self)")
        # global available,playing,awayfromkb
        self.available = {}
        self.playing = {}
        self.awayfromkb = {}

    def dispatch2(self,seq, data):

        # print "burasi calisti mi 10"
        # out of band data
        if seq == Protocol.CHAT_DATA:
            #print "buraya girdik mi hic (line:233)"
            self.parseChatResponse(data)
        elif seq == Protocol.PLAYER_STATE_CHANGE:
            self.parseStateChangesResponse(data)
        else:
            self.dispatchInbandData(seq, data)

    def dispatchInbandData(self, seq, data):
        #global tcpCommandsWaitingForResponse
        if not seq in self.tcpCommandsWaitingForResponse:
            #print "Sequence {} data {} not matched".format(seq, data)
            return

        origRequest = self.tcpCommandsWaitingForResponse[seq]
        del self.tcpCommandsWaitingForResponse[seq]

        if origRequest == Protocol.AUTH:
            self.parseAuthResponse(data)
        elif origRequest == Protocol.MOTD:
            self.parseMotdResponse(data)
        # elif origRequest == Protocol.LIST_CHANNELS:
        #     parseListChannelsResponse(data)
        elif origRequest == Protocol.LIST_USERS:
            self.parseListUsersResponse(data)
        # elif origRequest == Protocol.SPECTATE:
        #     status, data = Protocol.extractInt(data)
        #     if status != 0:
        #         self.sigStatusMessage.emit("Fail to spectate " + str(status))

    def parseAuthResponse(self, data):
        if len(data) < 4:
            # logdebug().error("Unknown auth response {}".format(repr(data)))
            return
        result, data = Protocol.extractInt(data)
        if result == 0:
            # self.selectTimeout = 15
            # self.sigLoginSuccess.emit()
            pass
        # password incorrect, user incorrect
        #if result == 0x6 or result == 0x4:
        else:
            if self.tcpSock:
                self.tcpSock.close()
                # self.tcpConnected = False
            #if self.udpSock:
            #    self.udpSock.close()
            #    self.udpConnected = False
            # self.sigLoginFailed.emit()
            #self.sigStatusMessage.emit("Login failed {}".format(result))
            self.exit()
            if result==6:
                self.message="Login failed: wrong password"
                # self.sigStatusMessage.emit("Login failed: wrong password")
            elif result==9:
                self.message="Login failed: too many connections"
                # self.sigStatusMessage.emit("Login failed: too many connections")
            elif result==4:
                self.message="Login failed: username doesn't exist into database"
                # self.sigStatusMessage.emit("Login failed: username doesn't exist into database")
            elif result==8:
                self.message="Clone connection closed.\nPlease login again."
                # self.sigStatusMessage.emit("Clone connection closed.\nPlease login again.")
            else:
                self.sigStatusMessage.emit("Login failed {}".format(result))
    def parseStateChangesResponse(self, data):
        count, data = Protocol.extractInt(data)
        while count > 0 and len(data) >= 4:
            state, p1, p2, playerinfo, data = self.__class__.extractStateChangesResponse(data)
            if state == PlayerStates.PLAYING:
                self.parsePlayerStartGameResponse(p1, p2, playerinfo)
                if self.username == p1:
                    self.playingagainst = p2
                if self.username == p2:
                    self.playingagainst = p1
                # if Settings.value(Settings.USER_LOG_PLAYHISTORY) and self.username in [p1, p2]:
                #     loguser().info(u"[IN A GAME] {} vs {}".format(p1, p2))
                # print("{} and {} in game".format(p1,p2))
            elif state == PlayerStates.AVAILABLE:
                self.parsePlayerAvailableResponse(p1, playerinfo)
                if self.playingagainst == p1:
                    self.playingagainst = ''
                #     self.killEmulator()
            elif state == PlayerStates.AFK:
                self.parsePlayerAFKResponse(p1, playerinfo)
                if self.playingagainst == p1:
                    self.playingagainst = ''
                #     self.killEmulator()
            elif state == PlayerStates.QUIT:
                self.parsePlayerLeftResponse(p1)
            else:
                # logdebug().error(
                #     "Unknown state change payload state: {} {}".format(state, repr(data)))
                print("respond degisiminde hata")
            # if state == PlayerStates.PLAYING:
            #     msg = p1 + ' ' + PlayerStates.codeToString(state) + ' ' + p2
            # else:
            #     msg = p1 + ' ' + PlayerStates.codeToString(state)
            # logdebug().info(msg)
            count -= 1

        #if len(data) > 0:
        #    logdebug().error("stateChangesResponse, remaining data {}".format(repr(data)))

    @staticmethod
    def extractStateChangesResponse(data):
        if len(data) >= 4:
            code, data = Protocol.extractInt(data)
            p1, data = Protocol.extractTLV(data)
            if code == 0:
                p2 = ''
                return PlayerStates.QUIT, p1, p2, None, data
            elif code != 1:
                # logdebug().error("Unknown player state change code {}".format(code))
                print("hata static method da")
            state, data = Protocol.extractInt(data)
            p2, data = Protocol.extractTLV(data)
            if not p2:
                p2 = "null"
            ip, data = Protocol.extractTLV(data)
            # \xff\xff\xff\x9f
            # \x00\x00\x00&
            unknown1, data = Protocol.extractInt(data)
            unknown2, data = Protocol.extractInt(data)
            city, data = Protocol.extractTLV(data)
            cc, data = Protocol.extractTLV(data)
            if cc:
                cc = cc.lower()
            country, data = Protocol.extractTLV(data)
            # \x00\x00\x17y
            marker, data = Protocol.extractInt(data)
            playerinfo = dict(
                player=p1,
                ip=ip,
                city=city,
                cc=cc,
                country=country,
                spectators=0,
            )
            return state, p1, p2, playerinfo, data

    def parsePlayerAvailableResponse(self, p1, playerinfo):
        self.addUser(**playerinfo)
        self.available[p1] = True
        self.awayfromkb.pop(p1, None)
        self.playing.pop(p1, None)
        #self.sigPlayerStateChange.emit(p1, self.AVAILABLE)
    def parsePlayerStartGameResponse(self, p1, p2, playerinfo):
        self.addUser(**playerinfo)
        self.playing[p1] = p2
        self.available.pop(p1, None)
        self.awayfromkb.pop(p1, None)
        #self.sigPlayerStateChange.emit(p1, PlayerStates.PLAYING)
    def parsePlayerAFKResponse(self, p1, playerinfo):
        self.addUser(**playerinfo)
        self.awayfromkb[p1] = True
        self.available.pop(p1, None)
        self.playing.pop(p1, None)
        #self.sigPlayerStateChange.emit(p1, PlayerStates.AFK)
    def parsePlayerLeftResponse(self, p1):
        if p1:
            self.available.pop(p1, None)
            self.awayfromkb.pop(p1, None)
            self.playing.pop(p1, None)



    def mainloop(self,e = 0):

        inputready, outputready, exceptready = select.select([self.tcpSock], [], [], self.selectTimeout)

        data = None

        if self.tcpSock in inputready:
            data = self.tcpSock.recv(16384)
            if not data:
                # print "server connection killed"
                pass
            else:
                self.tcpData += data
                self.handleTcpResponse()
        self.fillPlayers()


    def getPlayers(self):
        return [self.players,self.available,self.playing,self.awayfromkb]
    def login(self,name = " ",password = " ",room="sfa3"):
        try:
            self.tcpSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.tcpSock.connect(('ggpo-ng.com', 7000))
            except:
                # print "return 3"
                return 3

            self.sendAndRemember(Protocol.WELCOME, '\x00\x00\x00\x00\x00\x00\x00\x1d\x00\x00\x00\x01')
            self.sendAuth(name, password)


            self.sendToggleAFK(1)

            try:
                self.sendAndRemember(Protocol.JOIN_CHANNEL, Protocol.packTLV(room))
            except:
                # print "return 2"
                return 2
            self.sendAndRemember(Protocol.MOTD)
            self.sendAndRemember(Protocol.LIST_USERS)
            self.chatLog=""
            return 1
        except(Exception) as e:
            # print("connect_to_serverti basarisiz hata in loging === {}".format(e))
            self.tcpSock.close()
            return 0

class MyApplication(App):
    def build(self):

        return FightcadeCilent()


if __name__ == "__main__":
    # fc = FightcadeCilent()
    # fc.login()
    # while True:
    #     fc.mainloop()
    # Clock.schedule_interval(fc.mainloop,1)
    # threading.Thread(target = fc.alternative_loop())

    # while True:
    #     Clock.schedule_interval(myfunc,0)
    Config.set('graphics', 'width', '400')
    Config.set('graphics', 'height', '600')
    MyApplication().run()
