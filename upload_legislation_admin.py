from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import time
import re
from datetime import datetime, timedelta

# 📌 날짜 기준 (어제)
today = datetime.today()
yesterday = today - timedelta(days=1)

# 날짜 문자열 변환
today_str_mmdd = f"{today.month}/{today.day}"
yesterday_dash = yesterday.strftime("%Y-%m-%d")
yesterday_str_kor = f"{yesterday.month}월 {yesterday.day}일"

# 메일 제목
mail_subject_date = f"[{today_str_mmdd}] {yesterday_dash} 입법예고 입법다람이"

# 오늘 날짜 객체 (종료일 비교용)
today_date = today.date()

# 📌 Google Sheets 연동 함수
def connect_to_google_sheet(sheet_name, worksheet_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)

    client = gspread.authorize(creds)
    return client.open(sheet_name).worksheet(worksheet_name)

# 📌 의견제출 이전까지 내용만 추출
def extract_until_opinion(text):
    cut_keywords = ["3. 의견제출", "의견제출", "※ 제출의견", "의견 제출"]
    for key in cut_keywords:
        if key in text:
            return text.split(key)[0].strip()
    return text.strip()

# 📌 브라우저 설정
options = webdriver.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 10)

results = []

try:
    url = "https://opinion.lawmaking.go.kr/gcom/ogLmPp"
    driver.get(url)
    page_number = 1

    while True:
        print(f"\n📄 [페이지 {page_number}]")
        time.sleep(2)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#listView > ul")))
        link_elements = driver.find_elements(By.CSS_SELECTOR, "#listView > ul > li.title.W40 > a")

        for i in range(len(link_elements)):
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#listView > ul")))
            link_elements = driver.find_elements(By.CSS_SELECTOR, "#listView > ul > li.title.W40 > a")
            if i >= len(link_elements):
                break

            link = link_elements[i]
            try:
                driver.execute_script("arguments[0].click();", link)
            except:
                time.sleep(2)
                try:
                    driver.execute_script("arguments[0].click();", link)
                except:
                    print("❌ 클릭 실패 → 건너뜀")
                    continue

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ogLmPpVo")))

            try:
                title = driver.find_element(By.CSS_SELECTOR, "#ogLmPpVo > div:nth-child(7) > div > p:nth-child(8) > span").text.strip()
            except:
                title = "제목 없음"

            try:
                committee_raw = driver.find_element(By.CSS_SELECTOR, "#ogLmPpVo > ul.basic > li:nth-child(2) > table > tbody > tr > td").text.strip()
                committee = committee_raw.split("전화번호")[0].strip()
            except:
                committee = "소관위 없음"

            try:
                period_raw = driver.find_element(By.CSS_SELECTOR, "#ogLmPpVo > ul.basic > li:nth-child(1)").text.strip()
                match = re.search(
                    r"(\d{4})[.\- ]\s*(\d{1,2})[.\- ]\s*(\d{1,2})[.]?\s*~\s*(\d{4})[.\- ]\s*(\d{1,2})[.\- ]\s*(\d{1,2})",
                    period_raw
                )
                if match:
                    start_date = datetime.strptime(f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}", "%Y-%m-%d").date()
                    end_date = datetime.strptime(f"{match.group(4)}-{int(match.group(5)):02d}-{int(match.group(6)):02d}", "%Y-%m-%d").date()
                else:
                    print(f"❗ 날짜 추출 실패 → period_raw: {period_raw}")
                    start_date, end_date = None, None
            except Exception as e:
                print(f"❗ 날짜 파싱 예외 발생: {e}")
                start_date, end_date = None, None

            if not start_date or start_date.strftime("%Y-%m-%d") != yesterday_dash:
                print(f"⏩ 게시시작일({start_date}) ≠ 어제({yesterday_dash}) → 건너뜀")
                driver.back()
                time.sleep(2)
                continue

            if end_date and end_date < today_date:
                print(f"⏳ [SKIP] 마감일 경과 → {end_date}")
                driver.back()
                time.sleep(2)
                continue

            try:
                content_raw = driver.find_element(By.CSS_SELECTOR, "#ogLmPpVo > div:nth-child(7) > div").text.strip()
                content = extract_until_opinion(content_raw)
            except:
                content = "내용 없음"

            try:
                link_element = driver.find_element(By.CSS_SELECTOR, "#ogLmPpVo > ul:nth-child(2) > a:nth-child(2)")
                link_url = link_element.get_attribute("href").strip()
            except:
                link_url = "링크 없음"

            print(f"\n🔎 [{(page_number - 1) * 20 + i + 1}번째 입법예고]")
            print("📌 제목:", title)
            print("🏛️ 소관위:", committee)
            print("📅 게시시작일:", start_date)
            print("📅 게시종료일:", end_date)
            print("📝 내용 요약:", content)
            print("🔗 링크:", link_url)

            results.append([mail_subject_date, yesterday_str_kor, title, committee, end_date.strftime("%Y-%m-%d"), content, link_url])
            driver.back()
            time.sleep(2)

        # 📌 페이지네이션
        try:
            pagination = driver.find_elements(By.CSS_SELECTOR, "#nav > ol > li")
            next_clicked = False
            for li in pagination:
                a_tags = li.find_elements(By.TAG_NAME, "a")
                if a_tags and a_tags[0].text.strip() == str(page_number + 1):
                    driver.execute_script("arguments[0].click();", a_tags[0])
                    page_number += 1
                    next_clicked = True
                    break
            if not next_clicked:
                print("\n✅ 마지막 페이지까지 완료되었습니다.")
                break
        except Exception as e:
            print(f"\n❗ 페이지 이동 오류: {e}")
            break

finally:
    print("\n📤 구글시트 저장 중...")
    try:
        sheet = connect_to_google_sheet('최종입법데이터', '행정부')
        sheet.clear()
        sheet.append_row([
            "메일제목", "수집일", "제목", "소관위", "게시종료일",
            "주요내용", "링크", "요약본", "기대효과", "인덱스"
        ])

        if results:
            for idx, row in enumerate(results, start=1):
                row.extend(["", "", idx])  # 요약본, 기대효과, 인덱스
            sheet.append_rows(results)
            print(f"✅ 구글시트 저장 완료: 총 {len(results)}건 업로드됨")
        else:
            print("📂 저장할 데이터가 없습니다.")

    except Exception as e:
        print("❌ 구글시트 저장 실패:", e)

    driver.quit()


