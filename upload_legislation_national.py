import requests
import json
import time
import gspread
import schedule
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta

def main():
    today_date = datetime.today()
    yesterday_date = today_date - timedelta(days=1)

    today_str_mmdd = f"{today_date.month}/{today_date.day}"
    yesterday_dash = yesterday_date.strftime("%Y-%m-%d")
    yesterday_str_kor = f"{yesterday_date.month}월 {yesterday_date.day}일"
    mail_subject_date = f"[{today_str_mmdd}] {yesterday_dash} 입법예고 입법다람이"

    # STEP 1. API 수집
    API_KEY = "0e7398853c8b44c5bdb12c9726538bfc"
    BASE_URL = "https://open.assembly.go.kr/portal/openapi/nknalejkafmvgzmpt"
    api_data = {}
    page = 1
    while True:
        params = {"KEY": API_KEY, "Type": "json", "pIndex": page, "pSize": 100}
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        rows = data.get("nknalejkafmvgzmpt", [None, {}])[1].get("row", [])
        if not rows:
            break
        for bill in rows:
            noti_st_dt = bill.get("NOTI_ST_DT", "")
            if noti_st_dt != yesterday_dash:
                continue
            bill_no = bill.get("BILL_NO")
            api_data[bill_no] = {
                "의안번호": bill_no,
                "제목": bill.get("BILL_NAME", ""),
                "링크": bill.get("LINK_URL", ""),
                "소관위": bill.get("CURR_COMMITTEE", ""),
                "제안자": bill.get("PROPOSER", ""),
                "게시종료일": bill.get("NOTI_ED_DT", ""),
                "내용요약": "(내용 없음)"
            }
        print(f"✅ API pIndex={page} 수집 완료, 누적: {len(api_data)}개")
        page += 1

    # STEP 2. Selenium 크롤링
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--start-maximized')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)

    list_url = "https://pal.assembly.go.kr/napal/lgsltpa/lgsltpaOngoing/list.do?searchConClosed=0&menuNo=1100026"
    driver.get(list_url)

    max_pages = 11
    current_page = 1
    combined_rows = []

    try:
        while current_page <= max_pages:
            print(f"\n📄 [페이지 {current_page}] =============================")
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR,
                "#frm > div > div.board01.pr.td_center.board-added > table > tbody > tr"
            )))

            links = driver.find_elements(By.CSS_SELECTOR,
                "#frm > div > div.board01.pr.td_center.board-added > table > tbody > tr > td.align_left.td_block > a"
            )

            for i in range(len(links)):
                links = driver.find_elements(By.CSS_SELECTOR,
                    "#frm > div > div.board01.pr.td_center.board-added > table > tbody > tr > td.align_left.td_block > a"
                )
                try:
                    driver.execute_script("arguments[0].click();", links[i])
                    time.sleep(2)

                    try:
                        elem = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '/html/body/div[4]/div/div[4]/table/tbody/tr/td[1]'))
                        )
                        bill_no = elem.get_attribute("innerText").strip()
                    except:
                        bill_no = "(없음)"

                    try:
                        raw_title = driver.find_element(By.CSS_SELECTOR, "#content > div.legislation-heading > h3").text.strip()
                        if "]" in raw_title and "(" in raw_title:
                            title = raw_title.split("]")[-1].split("(")[0].strip()
                        else:
                            title = raw_title
                    except:
                        title = "(제목 없음)"

                    try:
                        proposer = driver.find_element(By.CSS_SELECTOR,
                            '#content > div.board01.pr.td_center.board-added > table > tbody > tr > td:nth-child(2)').text.strip()
                    except:
                        proposer = "(제안자 없음)"

                    try:
                        committee = driver.find_element(By.CSS_SELECTOR,
                            '#content > div.board01.pr.td_center.board-added > table > tbody > tr > td.td_block').text.strip()
                    except:
                        committee = "(소관위 없음)"

                    try:
                        period_text = driver.find_element(By.CSS_SELECTOR,
                            '#content > div.board01.pr.td_center.board-added > table > tbody > tr > td:nth-child(6)').text.strip()
                        noti_range = period_text.split("~")
                        noti_st_dt = noti_range[0].strip() if len(noti_range) >= 1 else ""
                        noti_ed_dt = noti_range[1].strip() if len(noti_range) >= 2 else ""
                        if noti_st_dt != yesterday_dash:
                            print(f"⏩ 게시시작일({noti_st_dt}) ≠ 어제({yesterday_dash}) → 건너뜀")
                            driver.back()
                            time.sleep(1)
                            continue
                    except:
                        noti_ed_dt = ""

                    try:
                        content = driver.find_element(By.CSS_SELECTOR, "#content > div.card-wrap > div:nth-child(1) > div").text.strip()
                        summary = content
                    except:
                        summary = "(내용 없음)"

                    if bill_no in api_data:
                        api_data[bill_no]["내용요약"] = summary
                        print(f"✏️ [{i+1}] API에 있음 → 내용요약 보완: {bill_no}")
                    else:
                        row = {
                            "의안번호": bill_no,
                            "제목": title,
                            "제안자": proposer,
                            "소관위": committee,
                            "링크": driver.current_url,
                            "게시종료일": noti_ed_dt,
                            "내용요약": summary
                        }
                        combined_rows.append(row)
                        print(f"🆕 [NEW][{i+1}] API 누락 → 수동 추가: {bill_no}")

                except Exception as e:
                    print(f"❌ [{i+1}] 클릭/크롤링 에러: {e}")
                driver.back()
                time.sleep(2)

            current_page += 1
            if current_page <= max_pages:
                try:
                    driver.execute_script("fnSearch(arguments[0])", current_page)
                    time.sleep(2)
                except Exception as e:
                    print(f"❌ 페이지 {current_page} 이동 실패: {e}")
                    break

    except Exception as e:
        print(f"❌ 전체 오류: {e}")
    driver.quit()

    # STEP 3. Google Sheets 업로드
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("project2-465201-e2afcd853cd9.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open("최종입법데이터").worksheet("입법부")
    existing_data = sheet.get_all_values()
    header = existing_data[0]
    existing_rows = existing_data[1:]

    if len(existing_rows) > 0:
        sheet.resize(rows=1)
        print(f"🧹 기존 데이터 {len(existing_rows)}건 전체 삭제 완료 ✅")

    rows_to_append = []

    for bill_no, info in api_data.items():
        row = [
            mail_subject_date,
            yesterday_str_kor,
            bill_no,
            info["제목"], info["제안자"], info["소관위"],
            info["링크"], info["게시종료일"],
            info.get("내용요약", "(내용 없음)"), "", ""
        ]
        rows_to_append.append(row)

    for row in combined_rows:
        row = [
            mail_subject_date,
            yesterday_str_kor,
            row["의안번호"],
            row["제목"], row["제안자"], row["소관위"],
            row["링크"], row["게시종료일"], row["내용요약"], "", ""
        ]
        rows_to_append.append(row)

    if rows_to_append:
        sheet.append_rows(rows_to_append)
        print(f"📤 Google Sheet 신규 업로드 완료: 총 {len(rows_to_append)}건 ✅")
    else:
        print("📂 추가할 신규 데이터가 없습니다.")

# ✅ 스케줄 등록: 매일 오전 10:00 실행
schedule.every().day.at("10:00").do(main)

print("⏰ 입법부 수집기 대기 중... (Ctrl+C로 종료)")

while True:
    schedule.run_pending()
    time.sleep(1)
