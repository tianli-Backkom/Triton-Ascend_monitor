"""Check published embedded data against the exact build artifact."""
import argparse,json,time,urllib.request
from quality import verify_page

def main():
    p=argparse.ArgumentParser();p.add_argument("url");p.add_argument("manifest");args=p.parse_args()
    manifest=json.load(open(args.manifest,encoding="utf-8"))
    for attempt in range(8):
        try:
            url=args.url.rstrip("/")+"/?build="+manifest["sha256"]
            with urllib.request.urlopen(url,timeout=30) as response: source=response.read().decode()
            verify_page(source,manifest)
            print("Published dashboard matches build:",manifest["collected_at"],manifest["npu_points"],"NPU points")
            return
        except Exception as exc:
            print("Verification attempt",attempt+1,str(exc),flush=True)
            if attempt==7: raise
            time.sleep(20)

if __name__=="__main__": main()
