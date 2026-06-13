import csv
import time
import random
from jsonpath import jsonpath
from DrissionPage import ChromiumPage, ChromiumOptions
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== 极速反检测配置 ==========
co = ChromiumOptions()
co.set_argument('--disable-blink-features=AutomationControlled')
co.set_argument(f'--user-agent={random.choice([
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
])}')
co.set_argument('--disable-infobars')
co.set_argument('--start-maximized')  # 最大化，减少渲染异常

def boss_login(page):
    page.get('https://www.zhipin.com/web/user/?ka=header-login')
    print('请在浏览器中扫码登录...')
    page.wait(10)
    print('登录完成')

def fetch_desc(page, job_id, index):
    """极速获取职位描述"""
    detail_url = f'https://www.zhipin.com/job_detail/{job_id}.html'
    try:
        tab = page.new_tab(detail_url)
        # 缩短等待时间
        tab.wait.ele_displayed('css:.job-sec-text', timeout=2.5)
        desc_element = tab.ele('css:.job-sec-text', timeout=0.5) or tab.ele('css:.job-detail', timeout=0.5)
        desc = desc_element.text.replace('\n', ' ').strip() if desc_element else ''
        tab.close()
        return index, desc
    except Exception as e:
        # 极速模式下忽略错误信息，避免打印过多拖慢速度
        try:
            tab.close()
        except:
            pass
        return index, ''

def process_response(resp_body):
    job_list = (jsonpath(resp_body, '$..jobList') or
                jsonpath(resp_body, '$..joblist') or
                jsonpath(resp_body, '$.zpData.jobList'))
    if not job_list:
        return []
    job_names = jsonpath(job_list, '$..jobName')
    if not job_names:
        return []

    salary_desc = jsonpath(job_list, '$..salaryDesc')
    job_degrees = jsonpath(job_list, '$..jobDegree')
    job_experiences = jsonpath(job_list, '$..jobExperience')
    intern_days = jsonpath(job_list, '$..daysPerWeekDesc')
    intern_months = jsonpath(job_list, '$..leastMonthDesc')
    brand_names = jsonpath(job_list, '$..brandName')
    city_names = jsonpath(job_list, '$..cityName') or jsonpath(job_list, '$..cityname')
    districts = jsonpath(job_list, '$..areaDistrict')
    business_districts = jsonpath(job_list, '$..businessDistrict')
    encrypt_ids = jsonpath(job_list, '$..encryptJobId') or jsonpath(job_list, '$..jobId')

    page_data = []
    for idx in range(len(job_names)):
        req = '无明确要求'
        if job_experiences and job_experiences[idx]:
            req = f'全职，要求{job_experiences[idx]}'
        elif intern_days and intern_months and intern_days[idx] and intern_months[idx]:
            req = f'实习，{intern_days[idx]}，{intern_months[idx]}'

        name = job_names[idx] or ''
        salary = salary_desc[idx] if salary_desc else ''
        degree = job_degrees[idx] if job_degrees else ''
        brand = brand_names[idx] if brand_names else ''
        city = city_names[idx] if city_names else ''
        district = districts[idx] if districts else ''
        b_district = business_districts[idx] if business_districts else ''
        address = f"{city}-{district}-{b_district}"
        job_id = encrypt_ids[idx] if encrypt_ids else ''

        page_data.append([name, salary, degree, req, brand, address, job_id])
    return page_data

def get_data(page_number):
    page = ChromiumPage(co)
    boss_login(page)

    # 打开武汉搜索页（缩短初始等待）
    page.get('https://www.zhipin.com/web/geek/job?city=101200100')
    time.sleep(1)   # 原2秒 → 1秒

    # 自动触发一次搜索，显示筛选栏
    page.run_js("""
        (function(){
            var input = document.querySelector('input[name="query"]') ||
                        document.querySelector('.ipt-search') ||
                        document.querySelector('input[placeholder*="搜索"]') ||
                        document.querySelector('input[type="text"]');
            if (input) { input.value = ''; }
            var btn = document.querySelector('.search-btn') ||
                      document.querySelector('.btn-search') ||
                      document.querySelector('button[type="submit"]') ||
                      document.querySelector('.search-form button') ||
                      document.querySelector('.ipt-search ~ div') ||
                      document.querySelector('.icon-search') ||
                      document.querySelector('[class*="search"]');
            if (btn) { btn.click(); return; }
            if (input) {
                var event = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                input.dispatchEvent(event);
            }
        })();
    """)
    try:
        page.wait.ele_displayed('css=.search-condition', timeout=3)
    except:
        pass
    print('筛选栏已就绪。')

    input('\n>>> 现在浏览器中自由设置筛选条件，确认无误后回到这里按回车开始抓取...')

    print('极速抓取启动...')
    page.listen.start('joblist')
    page.run_js("""
        (function(){
            var btn = document.querySelector('.search-btn') ||
                      document.querySelector('.btn-search') ||
                      document.querySelector('button[type="submit"]') ||
                      document.querySelector('.search-form button') ||
                      document.querySelector('.ipt-search ~ div') ||
                      document.querySelector('.icon-search') ||
                      document.querySelector('[class*="search"]');
            if (btn) { btn.click(); return; }
            var input = document.querySelector('input[name="query"]') ||
                        document.querySelector('.ipt-search') ||
                        document.querySelector('input[placeholder*="搜索"]') ||
                        document.querySelector('input[type="text"]');
            if (input) {
                var event = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                input.dispatchEvent(event);
            }
        })();
    """)

    # 第一页请求等待（缩短为8秒）
    first_valid_data = None
    for data in page.listen.steps(timeout=8):
        resp_body = data.response.body
        code = jsonpath(resp_body, '$.code')
        if code and code[0] == 0:
            if jsonpath(resp_body, '$..jobList') or jsonpath(resp_body, '$..joblist'):
                first_valid_data = data
                break

    if first_valid_data is None:
        print('未捕获到职位数据，请检查网络或页面。')
        return []

    job_list_temp = process_response(first_valid_data.response.body)
    if not job_list_temp:
        print('第一页无职位数据。')
        return []

    collected_pages = 1
    print(f'第{collected_pages}页抓取完成，累计{len(job_list_temp)}条')

    # 极速翻页
    while collected_pages < page_number:
        page.run_js('window.scrollTo(0, document.body.scrollHeight);')
        time.sleep(1)   # 极速等待

        got_new_page = False
        try:
            for data in page.listen.steps(timeout=4):  # 极速超时
                resp_body = data.response.body
                code = jsonpath(resp_body, '$.code')
                if not code or code[0] != 0:
                    continue
                page_data = process_response(resp_body)
                if page_data:
                    job_list_temp.extend(page_data)
                    collected_pages += 1
                    print(f'第{collected_pages}页抓取完成，累计{len(job_list_temp)}条')
                    got_new_page = True
                    break
        except:
            pass

        if not got_new_page:
            # 极速重试
            page.run_js('window.scrollTo(0, document.body.scrollHeight);')
            time.sleep(1)
            try:
                for data in page.listen.steps(timeout=3):
                    resp_body = data.response.body
                    code = jsonpath(resp_body, '$.code')
                    if not code or code[0] != 0:
                        continue
                    page_data = process_response(resp_body)
                    if page_data:
                        job_list_temp.extend(page_data)
                        collected_pages += 1
                        print(f'第{collected_pages}页抓取完成（重试成功）')
                        got_new_page = True
                        break
            except:
                pass

        if not got_new_page:
            print('可能已到最后一页，停止翻页。')
            break

    print(f'列表收集完成，共 {len(job_list_temp)} 个职位。开始极速获取描述...')

    # 极速并发获取描述（线程数提高至12）
    result_list = [None] * len(job_list_temp)
    max_workers = 12
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, row in enumerate(job_list_temp):
            job_id = row[-1]
            if job_id:
                future = executor.submit(fetch_desc, page, job_id, i)
                futures[future] = i
            else:
                result_list[i] = row[:6] + ['']
        for future in as_completed(futures):
            i, desc = future.result()
            result_list[i] = job_list_temp[i][:6] + [desc]

    return [r for r in result_list if r is not None]

def save_data(data_list):
    if not data_list:
        print('无数据')
        return
    with open('boss直聘_极速.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['工作名称', '薪资待遇', '学历要求', '全职/实习要求', '企业名称', '地址', '职位描述'])
        writer.writerows(data_list)
    print(f'保存成功，共{len(data_list)}条')

if __name__ == '__main__':
    page_number = int(input('请输入抓取页数：'))
    data_list = get_data(page_number)
    save_data(data_list)