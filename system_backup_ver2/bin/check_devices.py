import subprocess
try:
    res = subprocess.run(["aplay", "-l"], capture_output=True, text=True)
    print(res.stdout)
except Exception as e:
    print(e)
