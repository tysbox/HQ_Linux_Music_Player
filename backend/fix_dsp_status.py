fp = '/home/tysbox/HQ_Linux_Music_Player/backend/main.py'
with open(fp, 'r') as f:
    content = f.read()

# Fix the dsp_status endpoint - use c.cdsp_version instead of c.version()
old_status = '''    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect()
        v = c.version()
        c.disconnect()
        return {"status": "running", "version": v}'''

new_status = '''    try:
        c = CamillaClient("127.0.0.1", 1234)
        c.connect()
        version_info = c.cdsp_version
        st = c.general.state()
        c.disconnect()
        return {"status": "running", "version": version_info, "state": st}'''

if old_status in content:
    content = content.replace(old_status, new_status)
    print('FIX: Updated dsp_status to use correct CamillaClient API')
else:
    print('FIX: Pattern not found')

with open(fp, 'w') as f:
    f.write(content)
