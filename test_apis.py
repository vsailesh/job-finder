import requests
import json

def test_workday():
    print("--- Microsoft Workday ---")
    url = "https://jobs.careers.microsoft.com/us/en/search-results" # Wait, Microsoft doesn't use Workday anymore? Let's try mastercard
    # Actually let's use Mastercard
    url = "https://mastercard.wd1.myworkdayjobs.com/wday/cxs/client/CorporateCareers/jobs"
    payload = {"appliedFacets":{},"limit":20,"offset":0,"searchText":""}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    resp = requests.post(url, json=payload, headers=headers)
    print(resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2)[:500])
    except:
        print(resp.text[:500])

def test_apple():
    print("\n--- Apple ---")
    url = "https://jobs.apple.com/api/role/search"
    payload = {"query":"","filters":{"locations":["US"]},"page":1}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }
    resp = requests.post(url, json=payload, headers=headers)
    print(resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2)[:500])
    except:
        print(resp.text[:500])

if __name__ == "__main__":
    test_workday()
    test_apple()
