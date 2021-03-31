
# a truly minimal HTTP proxy

import os
import sys
import SocketServer
import BaseHTTPServer
import json
import urllib
import httplib
import hashlib
import subprocess
import ctypes
import time
import uuid

gPORT = 1234 
gTrackedInfo = {} 
gHttpd = None
gPathSep = "/"
gCurrentSubtree = ""
gTitles = []
gEnumWindows = None
gEnumWindowsProc = None
gGetWindowText = None
gGetWindowTextLength = None
gIsWindowVisible = None
gFindWindow = None
gSendMessage = None
gTrialDone = False
global gAcctKey
gAcctKey = ""
global gUserSettings
gUserSettings = "{}"
gUsername = "Anybody";
gUserDataFn = "";
gUserInfo = "";

def readInUserInfo():
    global gUserDataFn
    global gUserInfo
    if os.path.exists(gUserDataFn) == False:
        gUserInfo = "{\"view_info\":{},\"favorites\":[],\"prefs\":{\"save-warnings\":\"on\",\"warning-unsaved-change-threshold\":5,\"max-saved-navigation-history\":200,\"language\":\"English\",\"logging\":\"normal\",\"default-url\":\"www.duckduckgo.com\",\"user-confirms-ugly-remove\":\"on\",\"user-confirms-config-changes\":\"on\",\"allow-resource-id-reuse\":true}}"
        f = open(gUserDataFn,"w+")
        f.write(gUserInfo)
        f.close()
    else:
        f = open(gUserDataFn,"r")
        gUserInfo = f.read()
        f.close()

if sys.platform != "darwin" and sys.platform != "win32":
    print('This OS platform is not supported')
    sys.exit()

if len(sys.argv) > 1:
    isValidPort = True
    l = len(sys.argv[1])
    if l > 5 or l < 2:
        isValidPort = False
    for x in sys.argv[1]:
        if x < '0' or x > '9':
            isValidPort = False
            break
    if isValidPort:
        gPORT = int(sys.argv[1])
    else:
        print('invalid port number supplied')
        sys.exit()

if os.name == "posix":
    PIPE = subprocess.PIPE
    output = subprocess.Popen(['id -un'],stdin=PIPE, stdout=PIPE, stderr=PIPE,shell=True)        
    gUsername = str(output.communicate()[0]).strip()
else:
    gUsername = os.getenv('username')

print('the username acquired is: ' + gUsername)

usrDataDir = "user-data" + gPathSep + gUsername
if os.path.exists(usrDataDir) == False:
    os.makedirs(usrDataDir)

gUserDataFn = usrDataDir + gPathSep + "user-info.json"
readInUserInfo()

if os.path.exists("usage.json") == False:
    f = open("usage.json","w+")
    f.write("{\"start\":" + str(time.time()) + ",\"added-urls\":0,\"added-docs\":0,\"added-files\":0,\"added-context-nodes\":0,\"open-ops\":0,\"close-ops\":0}") 
    f.close()

if os.path.exists("udapp.log") == False:
    f = open("udapp.log","w+")
    f.write("- - - - - - - UD Application Log File - - - - - - \n")
    f.close()

if os.path.exists("js/settings.json"):
    f = open("js/settings.json")
    gUserSettings = f.read()
    f.close()

if os.path.exists("acct-key.txt"):
    f = open("acct-key.txt")
    gAcctKey = f.read()
    f.close()
else:
    suggestedKey = uuid.uuid4().hex
    #print("sending usage data: " + json.dumps(data))
    #body = urllib.urlencode(data)
    body = ""
    headers = {"Accept": "application/json","ACCT_TOKEN": suggestedKey}
    conn = httplib.HTTPConnection("unitraverse.com:80")
    if conn == None:
        print("Unable to communicate with unitraverse.com to set up account key")
        print("You must be online when when starting the udagent.py for the first time")
        sys.exit()
    try:
        conn.request("POST", "/create-acct.php", body, headers)
    except IOError, e:
        print("Please connect to the internet when running the 'udagent.py' for the first time")
        sys.exit()
    response = conn.getresponse()
    rsltJson = response.read()
    rsltOb = json.loads(rsltJson)
    if rsltOb == None:
        print("Unable to communicate with unitraverse.com to set up account key")
        print("You must be online when when starting the udagent.py for the first time")
        sys.exit()
    if rsltOb['scriptout'].find('key accepted') < 0:
        print("Suggested account key was not accepted, please try starting the agent again.")
        sys.exit()
    print(str(response.status) + " " + str(response.reason) + " 200 OK")
    print(rsltJson)
    gAcctKey = suggestedKey
    f = open("acct-key.txt","w+")
    f.write(str(gAcctKey))
    f.close()
    conn.close()

class Proxy(BaseHTTPServer.BaseHTTPRequestHandler):

    theCmd = ""
    theCargo = ""
    tabBuf = ""
    currentDir = os.getcwd()
    defaultURL = "www.google.com"
    xtnUrlMap = {}
    FS_ERROR_STR = "fs-item-error"

    class itemInfo():
        title = ""
        open = False
        controlled = True
        id = ""

    def addTrackedItem(s,tree,id,type,path,file,title,url,tab,tabInfo):
        global gTrackedInfo
        if not tree in gTrackedInfo:
            gTrackedInfo[tree] = {}
        gTrackedInfo[tree][id] = {}
        gTrackedInfo[tree][id]['type'] = type
        gTrackedInfo[tree][id]['path'] = path
        gTrackedInfo[tree][id]['filename'] = file
        gTrackedInfo[tree][id]['title'] = title
        gTrackedInfo[tree][id]['url'] = url
        gTrackedInfo[tree][id]['tab'] = tab
        gTrackedInfo[tree][id]['tabinfo'] = tabInfo

    def loadWindowsSpecificMethods(s):
        global gEnumWindows
        global gEnumWindowsProc
        global gGetWindowText
        global gGetWindowTextLength
        global gIsWindowVisible
        global gFindWindow
        global gSendMessage
        gEnumWindows = ctypes.windll.user32.EnumWindows
        gEnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
        gGetWindowText = ctypes.windll.user32.GetWindowTextW
        gGetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        gIsWindowVisible = ctypes.windll.user32.IsWindowVisible
        gFindWindow = ctypes.windll.user32.FindWindowW
        gSendMessage = ctypes.windll.user32.SendMessageW

    def getHash(s,str):
        return hashlib.sha224(str).hexdigest()

    def cleanCache(s):
        global gTrackedInfo
        for l in gTrackedInfo:
            del l[:]
        del gTrackedInfo[:]

    def fixPath(s,p):
        outPath = ""
        if os.name == "posix":
            outPath = p.replace(" ",r'\ ')
        else:
            outPath = p.replace("/","\\")
            outPath = "\"" + outPath.strip() + "\""
        return outPath

    def openFile(s,fullPath,ext):
        if os.name == "posix":
            print('about to call Popen for file: ' + fullPath)
            return subprocess.Popen(['open',fullPath])
        else:
            return subprocess.Popen(["start"," ",fullPath],shell=True)

    def openDocument(s,fullPath,ext):
        if os.name == "posix":
            return subprocess.Popen(['open','-W','-a','TextEdit',fullPath])
        else:
            return subprocess.Popen(["notepad.exe",fullPath],shell=False)

    def startResponse(s,httpCode,contentType):
        s.send_response(httpCode)
        s.send_header("Content-type",contentType) # "text/html")
        s.end_headers()

    def initResFile(s):
        f = open("res.json", "w+")
        f.write("{\"urls\":{},\"docs\":{},\"dirs\":{}}") 
        f.close()

    def unpackMessage(s,msg):
        marr = msg.split("%20")
        s.theCmd = marr[0]
        s.theCargo = marr[1]
        for i in range(2,len(marr)):
            s.theCargo += marr[i]

    def saveDirectory(s,dirPath):
        if os.path.isdir(dirPath):
            print('Error: directory \'' + dirPath + '\' already exists')
        else:
            os.makedirs(dirPath)
            print('saving directory: ' + dirPath)

    def streamToRemote(s,top,branchItems):
        global gPathSep
        for item in branchItems:
            if item == None:
                continue
            if 'parent' in item:
                print('about to create directory: ' + top + gPathSep + item['parent'])
                subprocess.call('mkdir ' + top + gPathSep + item['parent'],shell=True)
            else:
                continue
            if 'children' in item:
                s.streamToRemote(top + gPathSep + item['parent'],item['children'])

    def getValidSubpath(s,path):
        arr = path.split(os.path.sep)
        numValid = 0
        ancestors = ""
        sep = ""
        for cpnt in path:
            ancestors += sep
            if os.path.exists(ancestors + cpnt):
                numValid += 1
                ancestors += cpnt
            else:
                break
            sep = os.path.sep
        return numValid

    def fetchDirItemsJSON(s,targetDir):
        global gPathSep
        json = "["
        sep = ""
        for item in os.listdir(targetDir):
            if os.path.isfile(targetDir + gPathSep + item):
                itemJSON = sep + "{\"file\":\"" + item + "\"}"
            else:
                itemJSON = sep + "{\"dir\":\"" + item + "\"}"
            json += itemJSON
            sep = ","
        return json + "]"

    def getExternalItemsJSON(s,targetDir):
        global gPathSep
        json = "["
        sep = ""
        for item in os.listdir(targetDir):
            if os.path.isfile(targetDir + gPathSep + item):
                itemJSON = sep + "{\"file\":\"" + item + "\"}"
            else:
                itemJSON = sep + "{\"dir\":\"" + item + "\",\"items\":" + s.getExternalItemsJSON(targetDir + gPathSep + item) + "}"
            json += itemJSON
            sep = ","
        return json + "]"

    def getStringTable(s,language):
        global gPathSep
        f = open("languages" + gPathSep + language + gPathSep + "string-table.json")
        str = f.read()
        f.close()
        return str;

    def respondToMessage(s):
        global gCurrentSubtree
        global gTrackedInfo
        global gPathSep
        global gAcctKey
        global gUserSettings
        global gUsername
        global gUserDataFn
        theinfo = None
        if s.theCargo != None:
            theinfo = urllib.unquote_plus(urllib.unquote_plus(s.theCargo))
        else:
            print('expected message cargo was not found')
            sys.exit()
        if s.theCmd == "update:ONLOADINFO":
            updateData = json.loads(theinfo)
            treeGUID = updateData['treeId']
            if os.path.exists(treeGUID) == False:
                os.makedirs(treeGUID)
            user = "unknown"
            if sys.platform == "win32":
                s.loadWindowsSpecificMethods()
            resInfo = json.dumps(gTrackedInfo)
            stringTable = {}
            stringTable['lang'] = "English"
            userSettingsOb = json.loads(gUserSettings)
            if not userSettingsOb['language'] == "English":
                stringTable = json.loads(s.getStringTable(userSettingsOb['language']))
                stringTable['lang'] = str(userSettingsOb['language'])
            readInUserInfo()
            loadInfo = "{\"xtn-key\":\"" + str(updateData['xtn-key']) + "\",\"username\":\"" + gUsername.strip() + "\",\"res-info-data\":" + resInfo + ",\"acct-key\":\"" + gAcctKey + "\",\"lang-strings\":" + json.dumps(stringTable) + ",\"user-info\":" + gUserInfo + "}"
            #print('sending launch response: ' + loadInfo)
            s.wfile.write(loadInfo)
            return
			
        if s.theCmd == "updateTab:URL":
            print("hearing message from Chrome: " + s.theCargo)
            return

        if s.theCmd == "queue:URL":
            qdata = json.loads(theinfo)
            s.xtnUrlMap[str(qdata['xtn-key'])] = qdata['url']
            return

        if s.theCmd == "track:NEWTAB":
            rdata = json.loads(theinfo)
            s.addTrackedItem(rdata['resGrp'],rdata['resId'],'url',None,None,None,None,rdata['tabId'],None)
            print('added tracked tab: ')
            print(str(gTrackedInfo))

        if s.theCmd == "track:TAB":
            rdata = json.loads(theinfo)
            s.addTrackedItem(rdata['resGrp'],rdata['resId'],'url',None,None,None,None,rdata['tabId'],None)
            #xtnKey = str(rdata['xtn-key'])
            #if xtnKey in s.xtnUrlMap:
            #    s.wfile.write(s.xtnUrlMap[str(rdata['xtn-key'])])
            #else:
            #    s.wfile.write(s.defaultURL)
            return
        
        if s.theCmd == "track:RESINFO":
            msgData = json.loads(theinfo)
            ###HERE: Track data, do not respond
            #resInfo = json.dumps(gTrackedInfo)
            #rspns = "{\"xtn-key\":\"" + msgData['xtn-key'] + "\",\"resInfoData\":" + resInfo + "}"
            #print('response to request for res info:')
            #print(rspns)
            #s.wfile.write(rspns)
            return

        if s.theCmd == "mirror:LOCAL_IMAGE":
            linkData = json.loads(theinfo)
            xtnKey = linkData['xtn-key']
            src = linkData['src']
            arr = src.split('/')
            fn = arr[len(arr) - 1]
            guid = uuid.uuid4().hex
            basePath = linkData['vaultId']
            if os.path.exists(basePath) == False:
                os.makedirs(basePath)
            basePath = basePath + '/res/'
            if os.path.exists(basePath) == False:
                os.makedirs(basePath)
            basePath = basePath + guid
            if os.path.exists(basePath) == False:
                os.makedirs(basePath)
            dst = basePath + '/' + fn
            os.symlink(src,dst)
            s.wfile.write('{"xtn-key":"' + str(xtnKey) + '","image_full_path":"' + dst + '"}')
            return

        if s.theCmd == "quit:TAB":
            resdata = json.loads(theinfo)
            xtnKey = resdata['xtn-key']
            tabId = -1
            if resdata['resGrp'] in gTrackedInfo:
                if str(resdata['resId']) in gTrackedInfo[resdata['resGrp']]:
                    tabId = gTrackedInfo[resdata['resGrp']][str(resdata['resId'])]['tab'] 
                    del gTrackedInfo[resdata['resGrp']][str(resdata['resId'])]
            msg = '{"xtn-key":"' + xtnKey + '","tabId":' + str(tabId) + '}'
            if tabId == -1:
                print('Looking for resId: ')
                print(str(resdata['resId']))
                print('in groupId: ')
                print(str(resdata['resGrp']))
                print('Not finding tab id in: ')
                print(str(gTrackedInfo))
            s.wfile.write(msg)
            return
			
        if s.theCmd == "save:Tabs":
            tabBuf = s.theCargo
            print("cargo on updateTab:URL: " + s.tabBuf)
            return

        if s.theCmd == "save:LOCAL_DIR":
            dirPath = urllib.unquote_plus(urllib.unquote_plus(s.theCargo))
            if dirPath != None and len(dirPath) > 0:
                if dirPath[1:3] == ':\\\\' or dirPath[0:1] == '/':
                    s.saveDirectory(dirPath)
                else: 
	            console.log("Error: Invalid path information with save:LOCAL_DIR")
            else:
                console.log("Error: Invalid path information with save:LOCAL_DIR")
            return

        if s.theCmd == "add:DOC":
            docdata = json.loads(theinfo)
            xtnKey = docdata['xtn-key']
            docClass = docdata['doc-class']
            openNow = docdata['open-now']
            treeGUID = docdata['treeId']
            guid = ""
            if docClass != 'adopted':
                guid = uuid.uuid4().hex
            fn = docdata['filename'] + '.' + docdata['ext']
            basePath = docdata['basePath']
            relPath = docdata['relativePath']
            if basePath == "":
                basePath = os.getcwd() + gPathSep + treeGUID 
            path = basePath
            if relPath != "":
                path = basePath + gPathSep + relPath
            if docClass != 'adopted':
                path += gPathSep + 'res' + gPathSep + guid
                fullPath = path + gPathSep + fn
                if os.path.exists(fullPath) == False:
                    os.makedirs(path)
                    f = open(fullPath,"w+")
                    f.write("\n\t\t" + docdata['ttl'] + "\n\n")
                    f.flush()		
                    f.close()
            else:
                fullPath = path + gPathSep + fn
            status = "doc added"
            proc = None
            if openNow == "true":
                #time.sleep(3.3)
                print('attempting to open: ' + fullPath)
                proc = s.openDocument(fullPath,docdata['ext'])
                s.addTrackedItem(treeGUID,docdata['id'],'doc',path,fn,docdata['ttl'],None,None,None)
                status = "doc added and opened"
            s.wfile.write('{"xtn-key":"' + str(xtnKey) + '","status":"' + status + '","guid":"' + guid + '"}')
            return

        if s.theCmd == "open:FILE":
            docdata = json.loads(theinfo)
            xtnKey = docdata['xtn-key']
            treeGUID = docdata['treeId']
            fn = docdata['filename'] + '.' + docdata['ext']
            basePath = docdata['basePath']
            relPath = docdata['relativePath']
            if basePath == "":
                basePath = os.getcwd()
                if treeGUID != "":
                    basePath += gPathSep + treeGUID 
            path = basePath
            if relPath != "":
                path = basePath + gPathSep + relPath
            fullPath = path + gPathSep + fn
            print('attempting to open: ' + fullPath)
            proc = s.openFile(fullPath,docdata['ext'])
            status = "file opened, not tracked"
            s.wfile.write('{"xtn-key":"' + str(xtnKey) + '","status":"' + status + '"}')
            return

        if s.theCmd == "open:DOC":
            docdata = json.loads(theinfo)
            xtnKey = docdata['xtn-key']
            treeGUID = docdata['treeId']
            fn = docdata['filename'] + '.' + docdata['ext']
            basePath = docdata['basePath']
            relPath = docdata['relativePath']
            if basePath == "":
                basePath = os.getcwd() + gPathSep + treeGUID 
            path = basePath
            if relPath != "":
                path = basePath + gPathSep + relPath
            fullPath = path + gPathSep + fn
            print('attempting to open: ' + fullPath)
            proc = s.openDocument(fullPath,docdata['ext'])
            s.addTrackedItem(treeGUID,docdata['id'],'doc',path,fn,docdata['ttl'],None,None,None)
            status = "doc added and opened"
            s.wfile.write('{"xtn-key":"' + str(xtnKey) + '","status":"' + status + '"}')
            return

        if s.theCmd == "close:DOC":
            global gEnumWindows
            global gEnumWindowsProc
            global gTitles
            global gFindWindow
            global gSendMessage
            WM_CLOSE = "0x0010"
            closeInfo = json.loads(theinfo)
            treeGUID = closeInfo['treeId']
            if "id" in closeInfo: 
                trackedInfo = gTrackedInfo[treeGUID][closeInfo['id']]
                if os.name == "posix":
                    s.generateCloseScript(trackedInfo['path'],trackedInfo['filename'],trackedInfo['title'])
                    s.runScript()
                else:	
                    gEnumWindows(gEnumWindowsProc(s.foreach_window), 0)
                    for i in range(len(gTitles)):
                        fullName = trackedInfo['filename']
                        arr = fullName.split('.')
                        fn = ""
                        arrlen = len(arr)
                        for pos in range(arrlen):
                            if pos < arrlen - 1:
                                fn = fn + str(arr[pos])
                        thefile = fn.encode('ascii','ignore').strip()
                        asciiStr = gTitles[i][1].encode('ascii','ignore').strip()
                        if thefile in asciiStr:
                            #print('IN SUCCESSFUL')
                            if asciiStr.find(thefile,0) > -1:
                                hwnd = gFindWindow(None,gTitles[i][1])
                                #print('HWND: ' + str(hwnd))
                                if hwnd != None and hwnd != 0:
                                    #print('found hwnd: ' + str(hwnd) + ' for file \'' + fn)
                                    gSendMessage(hwnd,int(WM_CLOSE,16),None,None)
                                #else:
                                    #print('NO GO ON HWND')
                            #else:
                                #print('FIND NOT SUCCCESSFUL')
                del gTrackedInfo[treeGUID][closeInfo['id']]
            return
        
        if s.theCmd == "save:FS_ITEMS":
            #print("here is the save:FS_ITEMS saveData:")
            #print(theinfo)
            saveData = json.loads(theinfo)
            treeGUID = gCurrentSubtree = saveData['treeId']
            wudOutput = "{}"
            if 'usage' in saveData:
                wudOutput = s.writeUsageDataGetTotals(saveData)
            opList = saveData['ops']
            rsltStr = "save ops were successful"
            for op in opList: 
                pob = op['tgt']
                baseDir = pob['basePath']
                if baseDir == "": #only configured branches should make file system updates
                    continue
                relPath = pob['relativePath']
                if baseDir == "":
                    baseDir = os.getcwd() + gPathSep + treeGUID
                p = baseDir
                if relPath != "":
                    p = baseDir + gPathSep + relPath
                p2 = ""
                fullPath = ""
                opcd = op['opCode']
                rc = 0
                proc = None
                chkPath = ""
                chkPathNot = ""
                shellStr = ""
                if opcd == 'create_dir':
                    chkPath = baseDir + gPathSep + relPath
                    print('about to create dir: ' + chkPath)
                    try:
                        os.makedirs(chkPath) #on mac space characters are given backslashes by makedirs
                    except OSError as e:
                        print('udagent.py; create_dir; os.makedirs error')
                        print('Error number: ' + str(e.errno))
                        print('Error filename: ' + e.filename)
                        print('Error message: ' + e.strerror)
                        rsltStr = "(Udagent 'create_dir' error; Python os.makdirs; error #:" + str(e.errno) + " ;file:" + e.filename + " ;error str: " + e.strerror + ")"
                        #break
                if opcd == 'delete_dir':
                    print('about to remove dir: ' + p)
                    if os.name == "posix":
                        os.rmdir(p)
                    else:
                        shellStr = 'rmdir /s /q ' + p
                    chkPathNot = p
                if opcd == 'deep_delete_dir':
                    print('about to deep delete the dir: ' + p)
                    if os.name == "posix":
                        shellStr = './safeNukeDir.sh ' + treeGUID + ' ' + p
                    else:
                        shellStr = '.\\safeNukeDir.bat ' + p
                    chkPathNot = p
                if opcd == 'rename_dir':
                    p2 = p
                    p += gPathSep + op['oldLeaf']
                    p2 += gPathSep + op['newLeaf']
                    print('about to rename dir: ' + p + ' \n\tto: ' + p2)
                    if os.name == "posix":
                        shellStr = 'mv ' + p + ' ' + p2
                    else:
                        shellStr = 'rename ' + p + ' ' + op['newLeaf']
                    chkPathNot = p
                    chkPath = p2
                if opcd == 'create_res_copy' or opcd == 'create_sym_lnk':
                    srcOb = op['src']
                    p2 = srcOb['basePath'];
                    if p2 == "":
                        p2 = os.getcwd() + gPathSep + treeGUID
                    if srcOb['relativePath'] != "":
                        p2 = p2 + gPathSep + srcOb['relativePath']
                    fullPath = p2 + gPathSep + op['oldLeaf']
                    if os.path.exists(fullPath) == False:
                        if os.path.exists(p2) == False:
                            os.makedirs(p2)
                        print('about to open copy and/or symlink path : ' + fullPath)
                        try:
                            f = open(fullPath,'w')
                            f.flush()		
                            f.close()
                        except IOError as ioe:
                            print('udagent.py; ' + opcd + '; os.makedirs error')
                            print('Error number: ' + str(ioe.errno))
                            print('Error filename: ' + ioe.filename)
                            print('Error message: ' + ioe.strerror)
                            rsltStr = "(Udagent " + opcd + " error; Python open; error #:" + str(ioe.errno) + " ;file:" + ioe.filename + " ;error str: " + ioe.strerror + ")"
                        except OSError as e:
                            print('udagent.py; ' + opcd + '; os.makedirs error')
                            print('Error number: ' + str(e.errno))
                            print('Error filename: ' + e.filename)
                            print('Error message: ' + e.strerror)
                            rsltStr = "(Udagent " + opcd + " error; Python open; error #:" + str(e.errno) + " ;file:" + e.filename + " ;error str: " + e.strerror + ")"
                    if os.path.exists(fullPath):
                        if os.name == 'posix':
                            shellStr = 'cp ' + s.fixPath(fullPath) + ' ' + s.fixPath(p + gPathSep + op['newLeaf'])
                        else:
                            shellStr = 'copy ' + s.fixPath(fullPath) + ' ' + s.fixPath(p + gPathSep + op['newLeaf'])
                    chkPath = p + gPathSep
                if opcd == 'create_sym_lnk':
                    if os.name == 'posix':
                        shellStr = 'ln -s ' + s.fixPath(fullPath) + ' ' + s.fixPath(p + gPathSep + op['newLeaf'])
                    else:
                        shellStr = 'mklink /H ' + s.fixPath(p + gPathSep + op['newLeaf']) + ' ' + s.fixPath(fullPath)
                if opcd == 'create_script':
                    fullPath = p
                    fullPath += gPathSep + op['newLeaf']
                    f = open(fullPath,"w+")
                    f.write(op['content'])
                    f.flush()		
                    f.close()
                    os.chmod(fullPath,0755)
                if opcd == 'delete_res':
                    p = p + gPathSep + pob['filename'] + "." + pob['ext'] 
                    if os.name == 'posix':
                        shellStr = 'rm -f ' + p
                    else:
                        shellStr = 'del /q ' + p
                    chkPathNot = p
                if shellStr != "":
                    print('about to send this to Popen: ' + shellStr)
                    proc = subprocess.Popen(shellStr,shell=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    if proc != None:
                        output, err = proc.communicate()
                        rc = proc.returncode
                        if rc != 0:
                            rsltStr = "(Udagent error: Python subprocss(...) ;return code: " + str(rc) + " ;error string: " + err + ")" 
                            break
                chkPath = "" #getting stuck in polling wait after less than a dozen * x sleep calls
                if chkPath != "":
                    if s.pollForFileSystemChange(True,chkPath) == False:
                        rsltStr = "(Udagent error: check failure; wantExist:True; " + s.FS_ERROR_STR
                        print("Error: Not able to confirm existence of path: " + chkPath)
                        break
                if chkPathNot != "":
                    if s.pollForFileSystemChange(False,chkPathNot) == False:
                        rsltStr = "(Udagent error: check failure; wantExist:False; " + s.FS_ERROR_STR
                        print("Error: Not able to confirm non-existence of path: " + chkPathNot)
                        break
            print('save routine has completed')
            msg = '{"xtn-key":"' + saveData['xtn-key'] + '","result":"' + rsltStr + '","usage":' + wudOutput + '}'
            print('returned from udagent: ' + msg)
            s.wfile.write(msg)
            return

        if s.theCmd == "check:FS_ITEMS":
            checkData = json.loads(theinfo)
            treeGUID = checkData['treeId']
            checkList = checkData['checkList']
            replyStr = "fs-items-passed"
            for check in checkList:
                print('check being processed: ' + check['checkType']) 
                pob = check['tgt']
                baseDir = pob['basePath']
                relPath = pob['relativePath']
                if baseDir == "":
                    baseDir = os.getcwd() + gPathSep + treeGUID
                p = baseDir
                if relPath != "":
                    p = baseDir + gPathSep + relPath
                ctyp = check['checkType']
                if ctyp == 'dir_exists':
                    if os.path.exists(p) == False:
                        print('Error: this directory should exist but does not: ' + p)
                        replyStr = s.FS_ERROR_STR
                        break
                if ctyp == 'dir_exists_not':
                    if os.path.exists(p):
                        print('Error: this directory should not exist but does: ' + p)
                        replyStr = s.FS_ERROR_STR
                        break
                if ctyp == 'file_exists':
                    fpath = p + gPathSep + pob['filename'] + "." + pob['ext']
                    if os.path.exists(fpath) == False:
                        print('Error: this file should exist but does not: ' + fpath)
                        replyStr = s.FS_ERROR_STR
                        break 
                if ctyp == 'file_exists_not':
                    fpath = p + gPathSep + pob['filename'] + "." + pob['ext']
                    if os.path.exists(fpath):
                        print('Error: this file should not exist but does: ' + fpath)
                        replyStr = s.FS_ERROR_STR
                        break
 
            msg = "{\"xtn-key\":\"" + checkData['xtn-key'] + "\",\"result\":\"" + replyStr + "\"}"
            print('result message: ' + msg)
            s.wfile.write(msg)
            return



        if s.theCmd == "get:FS_ITEMS":
            requestInfo = json.loads(theinfo)
            numValid = s.getValidSubpath(requestInfo['targetDir'])
            fsdata = "{\"xtn-key\":\"" + str(requestInfo['xtn-key']) + "\",\"rootDir\":" + s.fetchDirItemsJSON(requestInfo['targetDir']) + ",\"num-valid-ancestors\":" + str(numValid) + "}"
            #print("here is the get:FS_ITEMS data:")
            #print(fsdata)
            print("returning data from get:FS_ITEMS request")
            s.wfile.write(fsdata)
            return  
        if s.theCmd == "save:SETTINGS":
            saveData = json.loads(theinfo)
            f = open(gUserDataFn,'w')
            if f is not None:
                if 'user-settings' in saveData:
                    usrInfo = json.loads(gUserInfo)
                    usrInfo['prefs'] = saveData['user-settings']
                    f.write(json.dumps(usrInfo))
                f.flush()		
                f.close()
            return  
        if s.theCmd == "save:EXTRANEOUS":
            #print("here is the save:EXTRANEOUS saveData:")
            #print(theinfo)
            #print("here is the user data path:")
            #print(gUserDataFn)
            saveData = json.loads(theinfo)
            f = open(gUserDataFn,'w')
            if f is not None:
                if 'user_data' in saveData:
                    f.write(json.dumps(saveData['user_data']))
                f.flush()		
                f.close()

            treeGUID = gCurrentSubtree = saveData['treeId']
            wudOutput = "{}"
            if 'usage' in saveData:
                wudOutput = s.writeUsageDataGetTotals(saveData)
            else:
                print("usage not specified in save data")
            opList = saveData['ops']
            rsltStr = "undetermined"
            for op in opList: 
                pob = op['tgt']
                baseDir = pob['basePath']
                if baseDir == "": #only configured branches should make file system updates
                    continue
                relPath = pob['relativePath']
                if baseDir == "":
                    baseDir = os.getcwd() + gPathSep + treeGUID
                p = baseDir
                if relPath != "":
                    p = baseDir + gPathSep + relPath
                p2 = ""
                fullPath = ""
                opcd = op['opCode']
                rc = 0
                proc = None
                chkPath = ""
                chkPathNot = ""
                shellStr = ""
                if opcd == 'create_dir':
                    chkPath = baseDir + gPathSep + relPath
                    print('about to create dir: ' + chkPath)
                    try:
                        os.makedirs(chkPath) #on mac space characters are given backslashes by makedirs
                    except OSError as e:
                        print('udagent.py; create_dir; os.makedirs error')
                        print('Error number: ' + str(e.errno))
                        print('Error filename: ' + e.filename)
                        print('Error message: ' + e.strerror)
                        rsltStr = "(Udagent 'create_dir' error; Python os.makdirs; error #:" + str(e.errno) + " ;file:" + e.filename + " ;error str: " + e.strerror + ")"
                        #break
                if opcd == 'delete_dir':
                    print('about to remove dir: ' + p)
                    if os.name == "posix":
                        os.rmdir(p)
                    else:
                        shellStr = 'rmdir /s /q ' + p
                    chkPathNot = p
                if opcd == 'deep_delete_dir':
                    print('about to deep delete the dir: ' + p)
                    if os.name == "posix":
                        shellStr = './safeNukeDir.sh ' + treeGUID + ' ' + p
                    else:
                        shellStr = '.\\safeNukeDir.bat ' + p
                    chkPathNot = p
                if opcd == 'rename_dir':
                    p2 = p
                    p += gPathSep + op['oldLeaf']
                    p2 += gPathSep + op['newLeaf']
                    print('about to rename dir: ' + p + ' \n\tto: ' + p2)
                    if os.name == "posix":
                        shellStr = 'mv ' + p + ' ' + p2
                    else:
                        shellStr = 'rename ' + p + ' ' + op['newLeaf']
                    chkPathNot = p
                    chkPath = p2
                if opcd == 'create_res_copy' or opcd == 'create_sym_lnk':
                    srcOb = op['src']
                    p2 = srcOb['basePath'];
                    if p2 == "":
                        p2 = os.getcwd() + gPathSep + treeGUID
                    if srcOb['relativePath'] != "":
                        p2 = p2 + gPathSep + srcOb['relativePath']
                    fullPath = p2 + gPathSep + op['oldLeaf']
                    if os.path.exists(fullPath) == False:
                        if os.path.exists(p2) == False:
                            os.makedirs(p2)
                        print('about to open copy and/or symlink path : ' + fullPath)
                        try:
                            f = open(fullPath,'w')
                            f.flush()		
                            f.close()
                        except IOError as ioe:
                            print('udagent.py; ' + opcd + '; os.makedirs error')
                            print('Error number: ' + str(ioe.errno))
                            print('Error filename: ' + ioe.filename)
                            print('Error message: ' + ioe.strerror)
                            rsltStr = "(Udagent " + opcd + " error; Python open; error #:" + str(ioe.errno) + " ;file:" + ioe.filename + " ;error str: " + ioe.strerror + ")"
                        except OSError as e:
                            print('udagent.py; ' + opcd + '; os.makedirs error')
                            print('Error number: ' + str(e.errno))
                            print('Error filename: ' + e.filename)
                            print('Error message: ' + e.strerror)
                            rsltStr = "(Udagent " + opcd + " error; Python open; error #:" + str(e.errno) + " ;file:" + e.filename + " ;error str: " + e.strerror + ")"
                    if os.path.exists(fullPath):
                        if os.name == 'posix':
                            shellStr = 'cp ' + s.fixPath(fullPath) + ' ' + s.fixPath(p + gPathSep + op['newLeaf'])
                        else:
                            shellStr = 'copy ' + s.fixPath(fullPath) + ' ' + s.fixPath(p + gPathSep + op['newLeaf'])
                    chkPath = p + gPathSep
                if opcd == 'create_sym_lnk':
                    if os.name == 'posix':
                        shellStr = 'ln -s ' + s.fixPath(fullPath) + ' ' + s.fixPath(p + gPathSep + op['newLeaf'])
                    else:
                        shellStr = 'mklink /H ' + s.fixPath(p + gPathSep + op['newLeaf']) + ' ' + s.fixPath(fullPath)
                if opcd == 'create_script':
                    fullPath = p
                    fullPath += gPathSep + op['newLeaf']
                    f = open(fullPath,"w+")
                    f.write(op['content'])
                    f.flush()		
                    f.close()
                    os.chmod(fullPath,0755)
                if opcd == 'delete_res':
                    p = p + gPathSep + pob['filename'] + "." + pob['ext'] 
                    if os.name == 'posix':
                        shellStr = 'rm -f ' + p
                    else:
                        shellStr = 'del /q ' + p
                    chkPathNot = p
                if shellStr != "":
                    print('about to send this to Popen: ' + shellStr)
                    proc = subprocess.Popen(shellStr,shell=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                    if proc != None:
                        output, err = proc.communicate()
                        rc = proc.returncode
                        if rc != 0:
                            rsltStr = "(Udagent error: Python subprocss(...) ;return code: " + str(rc) + " ;error string: " + err + ")" 
                            break
                chkPath = "" #getting stuck in polling wait after less than a dozen * x sleep calls
                if chkPath != "":
                    if s.pollForFileSystemChange(True,chkPath) == False:
                        rsltStr = "(Udagent error: check failure; wantExist:True; " + s.FS_ERROR_STR
                        print("Error: Not able to confirm existence of path: " + chkPath)
                        break
                if chkPathNot != "":
                    if s.pollForFileSystemChange(False,chkPathNot) == False:
                        rsltStr = "(Udagent error: check failure; wantExist:False; " + s.FS_ERROR_STR
                        print("Error: Not able to confirm non-existence of path: " + chkPathNot)
                        break
            if 'user_data' in saveData:
                print('found user_data')
                if os.path.exists(gUserDataFn) == False:
                    f = open(gUserDataFn)
                    f.write(saveData['user_data'])
                    f.close() 
            print('save routine has completed')
            msg = '{"xtn-key":"' + saveData['xtn-key'] + '","result":"' + rsltStr + '","usage":' + wudOutput + '}'
            print('returned from udagent: ' + msg)
            s.wfile.write(msg)
            return

        if s.theCmd == "reset:STARTER":
            if os.name == 'posix':
                subprocess.call('./resetStarter.sh',shell=True)
            else:
                subprocess.call('.\\resetStarter.bat',shell=True)
            return

        if s.theCmd == "establish:BRANCH":
            print('BRANCH INFO: \n' + s.theinfo)
            branchData = json.loads(theinfo)
            treeGUID = branchData['treeId']
            top = os.getcwd() + gPathSep + treeGUID + gPathSep + branchData['parent']
            targetDir = branchData['targetDir']
            print('about to mv')
            subprocess.call('mv ' + top + '/* ' + targetDir + '/',shell=True)        
            print('about to rm')
            subprocess.call('rm -rf ' + top,shell=True)
            print('about to ln')
            subprocess.call('ln -s ' + targetDir + ' ' + top,shell=True)
            print('about to echo')
            subprocess.call("echo \"This is a directory designated for i/o from the Unitraverse Desktop Application\" > " + top + "/ud-memo.txt",shell=True)
            fsItems = "{\"xtn-key\":\"" + str(branchData['xtn-key']) + "\",\"items\":" + s.getExternalItemsJSON(targetDir) + "}"
            s.streamToRemote(top,branchData['children'])
            s.wfile.write(fsItems)
            return

        if s.theCmd == "fetch:FILECONTENTS":
            rqstData = json.loads(theinfo)
            print(theinfo)
            fileData = ""
            #fn = (rqstData['file']).strip().replace("[bkslash]","\\")
            fn = (rqstData['file']).strip()
            print('the requested file is: ' + fn)
            if fn is not None:
                f = open(fn,'r')
                fileData = f.read().strip()
                fileData = fileData.replace("@","[klammeraffe]").replace("\t","[tab]")
                fileData = fileData.replace("\"","[dbqt]").replace("\n","[newline]")
                fileData = fileData.replace("<","&lt;").replace(">","&gt;")
                fileData = fileData.replace("'","[sglqt]").replace("\\","[bkslash]")
                f.close()
            s.wfile.write("{\"xtn-key\":\"" + str(rqstData['xtn-key']) + "\",\"data\":\"" + fileData + "\"}")
            #print("FILE DATA:")
            #print(fileData)
            #print("END FILE DATA")
            return
 
        if s.theCmd == "fetch:DIRCONTENTS":
            rqstData = json.loads(theinfo)
            print(theinfo)
            dirData = ""
            fileData = ""
            pth = (rqstData['path']).strip()
            print('the requested path is: ' + pth)
            thefiles = os.listdir(pth)
            listSep = ""
            fListSep = ""
            pSep = gPathSep
            if pth[len(pth) - 1] == gPathSep:
                pSep = "" 
            for f in thefiles:
                if os.path.isfile(pth + pSep + f):
                    fileData += fListSep + "\"" + f + "\""
                    fListSep = ","
                else:
                    dirData += listSep + "\"" + f + "\""
                    listSep = ","
            #if pth is not None:
                #dirData = dirData.replace("\"","[dbqt]").replace("\n","[newline]")
                #dirData = dirData.replace("'","[sglqt]").replace("\\","[bkslash]")
            dirData = "{\"directories\":[" + dirData + "],\"files\":[" + fileData + "]}"
            #print("DIR DATA:")
            #print(dirData)
            #print("END DIR DATA")
            s.wfile.write("{\"xtn-key\":\"" + str(rqstData['xtn-key']) + "\",\"data\":" + dirData + "}")
            return
      
        if s.theCmd == "split2natfiles:FILE":
            rqstData = json.loads(theinfo)
            treeGUID = rqstData['treeId']
            print(theinfo)
            guid = uuid.uuid4().hex
            fileData = []
            fn = (rqstData['path']).strip() + gPathSep + (rqstData['filename']).strip()
            f = open(fn,'r')
            if f is not None:
                fileDataArr = f.read().splitlines()
                f.close()
                basePath = os.getcwd() + gPathSep + treeGUID + gPathSep + "res"
                basePath += gPathSep + guid
                os.makedirs(basePath)
                basePath += gPathSep + (rqstData['filename']).strip('.txt')
                chunkArr = rqstData['lines']
                num = 1
                for chunk in chunkArr:
                    print('chunk: ' + str(chunk))
                    nufn = basePath + "_part" + str(num) + ".txt"
                    outf = open(nufn,'w+')
                    if outf is not None:
                        for pos in range(chunk['l1'],chunk['l2']):
                            outf.write(fileDataArr[pos])
                        outf.close()
                        num += 1
            s.wfile.write("{\"xtn-key\":\"" + str(rqstData['xtn-key']) + "\",\"responseData\":\"" + basePath + "\"}")
            return

        if s.theCmd == "log:MSG":
            logInfo = json.loads(theinfo)
            f = open("udapp.log","a")
            logMsg = logInfo['msg'].replace("[newline]","\n")
            f.write(logMsg + "\n")
            f.close()

        s.wfile.write("error: unknown udagent command: " + s.theCmd) 

    def generateCloseScript(s,docPath,docName,docTitle):
        scriptStr = ""
        fn = ""
        if os.name == "posix":
            fn = "action.applescript"
            scriptStr = "set theFile to \"" + docPath + "/" + docName + "\"\ntell application \"TextEdit\" \n\tset AllWindows to a reference to every window\n\trepeat with aWindow in AllWindows\n\t\tif path of document of aWindow is equal to theFile then\n\t\t\tclose document of aWindow without saving\n\t\t\texit repeat\n\t\tend if\n\tend repeat\nend tell"
        else:
            fn = "action.vbs"
            scriptStr = "Set oShell = CreateObject(\"WScript.Shell\") \nWscript.Sleep 1000 \nIf oShell.AppActivate(\"" + docTitle + " - Notepad\") Then\n WScript.Sleep 1500 \noShell.SendKeys \"%{F4}\"\nEnd If"		
        f = open(fn,'w')
        f.write(scriptStr)
        f.close()
  
    def runScript(s):
        path = ""
        if os.name == "posix":
            path = s.currentDir + '/action.applescript'  
            os.chmod(path,0777) # stat.S_IXUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            proc = subprocess.Popen(['/usr/bin/osascript',path])
            proc.communicate() #need this to make it block            
        else:
            path = s.currentDir + '/action.vbs'
            #os.chmod(path,0777) # stat.S_IXUSR | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            subprocess.Popen(['wscript.exe',path],shell=True)       	

    def pollForFileSystemChange(s,wantExist,path):
        while True:
            if wantExist:
                if os.path.exists(path):
                    return True
            else:
                if os.path.exists(path) == False:
                    return True
            time.sleep(0.3)

    def foreach_window(s,hwnd,lParam):
        global gIsWindowVisible
        global gGetWindowTextLength
        global gGetWindowText
        global gTitles
        if gIsWindowVisible(hwnd):       
            length = gGetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            gGetWindowText(hwnd, buff, length + 1)
            gTitles.append((hwnd, buff.value))
        return True		

    def sendUsageData(s,data):
        global gAcctKey	
        print("sending usage data: " + json.dumps(data))
        body = urllib.urlencode(data)
        acctkey = gAcctKey.strip()
        headers = {"Accept": "application/json", "ACCT_TOKEN": acctkey}
        conn = httplib.HTTPConnection("unitraverse.com:80")
        conn.request("POST", "/usage.php", body, headers)
        response = conn.getresponse()
        rsltJson = response.read()
        print("python conn.getresponse() returned response.status: " + str(response.status) + " response.reason: " + str(response.reason))
        if rsltJson == None:
            print('No response message from usage API')
        conn.close()
        return rsltJson

    def writeUsageDataGetTotals(s,saveJSON):
        global gTrialDone
        updateUsage = False
        f = open('usage.json')
        past = json.load(f)
        f.close()
        incoming = saveJSON['usage']
        total = {}
        total['start'] = past['start']
        total['now'] = str(time.time());
        total['added-urls'] = past['added-urls'] + incoming['added-urls']
        total['added-docs'] = past['added-docs'] + incoming['added-docs']
        total['added-files'] = past['added-files'] + incoming['added-files']
        total['added-context-nodes'] = past['added-context-nodes'] + incoming['added-context-nodes']
        total['open-ops'] = past['open-ops'] + incoming['open-ops']
        total['close-ops'] = past['close-ops'] + incoming['close-ops']
        totalActions = total['added-docs'] + total['added-urls'] + total['added-files'] + total['added-context-nodes'] + total['open-ops'] + total['close-ops'] 
        days = (float(past['start']) - time.time()) / 86400
        if days > 3 or totalActions > 60:
            if totalActions > 60:
                updateUsage = True
        f = open("usage.json", "w")
        # NOTE: IT IS A VIOLATION OF THE SOFTWARE LICENSING TERMS TO ALTER CODE RELATED TO PAYMENT REMINDERS
        # PLEASE REFER TO THE LICENSE AGREEMENT!!
        sendRslt = None
        if updateUsage:
            sendRslt = s.sendUsageData(total)
            f.write("{\"start\":" + str(time.time()) + ",\"added-urls\":0,\"added-docs\":0,\"added-files\":0,\"added-context-nodes\":0,\"open-ops\":0,\"close-ops\":0}") 
        else:
            f.write("{\"start\":" + str(past['start']) + ",\"added-urls\":" + str(total['added-urls']) + ",\"added-docs\":" + str(total['added-docs']) + ",\"added-files\":" + str(total['added-files']) + ",\"added-context-nodes\":" + str(total['added-context-nodes']) + ",\"open-ops\":" + str(total['open-ops']) + ",\"close-ops\":" + str(total['close-ops']) + "}") 
        f.close()
        tdstr = "false"
        if gTrialDone:
            tdstr = "true"
        udstr = "false"
        if updateUsage:
            udstr = "true"
        if sendRslt == None:
            sendRslt = "null";
        #return "{\"trial-done\":" + str(gTrialDone) + ",\"api-response\":" + sendRslt + ",\"usage-info\":" + json.dumps(total) + ",\"new-report-span\":" + str(updateUsage) + "}"
        return "{\"trial-done\":" + tdstr + ",\"api-response\":" + sendRslt + ",\"usage-info\":" + json.dumps(total) + ",\"new-report-span\":" + udstr + "}"
	
    def do_GET(s):
        msgDex = s.path.find("msg=")
        if msgDex > -1:
            s.startResponse(200,"text/html")
            s.unpackMessage(str(s.path[(msgDex + 4):])) # 5 and -1 to strip msg=" and "
            s.respondToMessage()
            return
        fpath = ""
        if s.path[:1] == "/":
            fpath = s.path[1:]
        else:
            fpath = s.path
        fpath = fpath.replace("%20"," ")
        mimeType = ""
        if ".html" in fpath:
            mimeType = "text/html"
            if fpath.find('?') != -1:
                fpath = fpath[0:fpath.index('?')]
        if ".js" in fpath:
            mimeType = "text/javascript"
        if ".css" in fpath:
            mimeType = "text/css"
        if "/images/" in s.path or "/res/" in s.path:
            imgType = ""
            if ".png" in fpath or ".PNG" in fpath:
                imgType = "png"
            if ".jpg" in fpath or ".JPG" in fpath:
                imgType = "jpg"
            if ".jpeg" in fpath or ".JPEG" in fpath:
                imgType = "jpeg"
            if ".ico" in fpath or ".ICO" in fpath:
                imgType = "x-icon"
            if imgType != "":
                mimeType = "image/" + imgType 
        if mimeType != "":
            rcode = 404
            if os.path.exists(fpath):
                rcode = 200
            s.startResponse(rcode,mimeType)
            f = open(fpath,"rb")
            s.wfile.write(f.read())
            return
        if s.path == "/testfile":
            s.startResponse(200,"text/html")
            f = open("updatetab.html","r")
            s.wfile.write(f.read()) 
            return
        if s.path == "/test":
            s.startResponse(200,"text/html")
            s.wfile.write("<html><head><title>Title goes here.</title></head>")
            s.wfile.write("<body><p>This is a test.</p>")
            s.wfile.write("<p>You accessed path: %s</p>" % s.path)
            dex = s.path.find("?")
            if dex > -1 :
                s.wfile.write("<p>the params are:" + str(s.path[(dex + 1):]) + " </p>") 
            s.wfile.write("<p>the raw requestline is : " + s.raw_requestline + " </p>")
            s.wfile.write("</body></html>")
            return
        s.startResponse(404,"text/html")
        s.wfile.write("<html><h3>Sorry, not finding the requested page " + s.path + " </html>")

    def do_POST(s):
        global gPathSep
        global gCurrentSubtree
        content_len = int(s.headers.getheader('m-len', 0))
        content = s.rfile.read(content_len)
        s.unpackMessage(content[4:]) # 4 to strip msg="
        #print('s.theCargo')
        #print(s.theCargo)
        theinfo = urllib.unquote_plus(urllib.unquote_plus(s.theCargo))
        #print('theinfo')
        #print(theinfo)
        f = open("js" + gPathSep + gCurrentSubtree + ".js",'w')
        #f = open("js" + gPathSep + "testEnc.js",'w') 
        f.write(theinfo)
        f.close()
        s.wfile.write("bytes recieved: " + str(len(theinfo)))

startFilePath = "udapp" + os.path.sep + "license" + os.path.sep + "agreement" + os.path.sep + "policy" + os.path.sep + "expressly" + os.path.sep + "prohibits" + os.path.sep + "tampering" + os.path.sep + "with" + os.path.sep + "this" + os.path.sep + "file" + os.path.sep
if os.path.exists(startFilePath) == False:
    os.makedirs(startFilePath)
    f = open(startFilePath + "first-run.json","w+")
    f.write("{\"trial-start\":" + str(time.time()) + "}") 
    f.close()
else:
    f = open(startFilePath + "first-run.json","r")
    startInfo = json.load(f)
    elapsedDays = (time.time() - float(startInfo['trial-start'])) / 86400
    # NOTE: IT IS A VIOLATION OF THE SOFTWARE LICENSING TERMS TO ALTER CODE RELATED TO THE TRIAL PERIOD 
    # PLEASE REFER TO THE LICENSE AGREEMENT!!
    daysLeft = 45 - elapsedDays
    if daysLeft > 0:
        print('days left to end of trial period:')
        print(str(daysLeft))
    gTrialDone = (daysLeft <= 0)

gHttpd = SocketServer.TCPServer(('localhost',gPORT), Proxy)
print("serving at port", gPORT)
gHttpd.serve_forever()

