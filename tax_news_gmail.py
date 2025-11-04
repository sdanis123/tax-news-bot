import requests
from bs4 import BeautifulSoup
from datetime import datetime
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import xml.etree.ElementTree as ET

# 설정값
GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS', "YOUR_GMAIL@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', "YOUR_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', "YOUR_EMAIL@gmail.com")
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', "YOUR_OPENAI_API_KEY")

def fetch_article_content(url):
    """기사 본문 가져오기"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 본문 추출 (다양한 패턴 시도)
        content = ""
        
        # 일반적인 뉴스 본문 패턴들
        patterns = [
            'article-body', 'news-body', 'article_body', 'newsBody',
            'article-content', 'news-content', 'article_content',
            'detail-content', 'view-content', 'article_txt'
        ]
        
        for pattern in patterns:
            element = soup.find('div', class_=lambda x: x and pattern in x)
            if element:
                content = element.get_text(strip=True)
                break
        
        # 찾지 못했으면 article 태그 시도
        if not content:
            article = soup.find('article')
            if article:
                content = article.get_text(strip=True)
        
        # 너무 짧으면 실패로 간주
        if len(content) < 100:
            return ""
        
        return content[:2000]  # 최대 2000자
        
    except Exception as e:
        print(f"  본문 가져오기 실패: {e}")
        return ""

def scrape_google_news():
    """구글 뉴스에서 조세 관련 뉴스 수집"""
    all_news = []
    
    # 수집할 언론사
    allowed_sources = [
        '한국세정신문', '조세일보', '세정일보', 
        '세무사신문', '택스워치', '조세금융신문'
    ]
    
    # 조세 관련 키워드
    tax_keywords = [
        '소득세', '부가가치세', '법인세', '상속세', 
        '증여세', '양도소득세', '종합부동산세', '취득세'
    ]
    
    try:
        print(f"조세 전문 뉴스 수집 중... (대상: {', '.join(allowed_sources)})")
        
        for keyword in tax_keywords:
            # when:1d = 최근 24시간 이내
            url = f"https://news.google.com/rss/search?q={keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
            
            try:
                response = requests.get(url, timeout=15)
                response.encoding = 'utf-8'
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                
                for item in items:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    source_elem = item.find('source')
                    
                    if title_elem is not None and link_elem is not None:
                        title = title_elem.text
                        link = link_elem.text
                        source = source_elem.text if source_elem is not None else ''
                        
                        # 발행일 확인 (오늘 기사만)
                        pubdate_elem = item.find('pubDate')
                        if pubdate_elem is not None:
                            from datetime import datetime, timedelta
                            try:
                                pub_date_str = pubdate_elem.text
                                # RSS 날짜 형식 파싱 (예: Mon, 04 Nov 2025 14:30:00 GMT)
                                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z')
                                today = datetime.utcnow().date()
                                
                                # 오늘 발행된 기사가 아니면 스킵
                                if pub_date.date() != today:
                                    continue
                            except:
                                pass  # 날짜 파싱 실패하면 일단 포함
                        
                        # 지정된 언론사만
                        if any(allowed in source for allowed in allowed_sources):
                            # 조세 관련 키워드가 제목에 있는지 확인
                            if any(tax_kw in title for tax_kw in tax_keywords):
                                # 중복 체크
                                if not any(news['title'] == title for news in all_news):
                                    print(f"  ✓ [{source}] {title[:50]}")
                                    
                                    # 기사 본문 가져오기
                                    print(f"    본문 가져오는 중...")
                                    content = fetch_article_content(link)
                                    
                                    if content:
                                        all_news.append({
                                            'site': source,
                                            'title': title,
                                            'link': link,
                                            'content': content,
                                            'keyword': keyword
                                        })
                                        print(f"    ✓ 본문 수집 완료 ({len(content)}자)")
                                    else:
                                        # 본문 없어도 제목만으로 저장
                                        all_news.append({
                                            'site': source,
                                            'title': title,
                                            'link': link,
                                            'content': title,  # 제목으로 대체
                                            'keyword': keyword
                                        })
                                        print(f"    ⚠ 본문 없음, 제목만 사용")
                                    
                                    # 10개 이상 수집하면 중단
                                    if len(all_news) >= 15:
                                        break
                
                if len(all_news) >= 15:
                    break
                    
            except Exception as e:
                print(f"  {keyword} 키워드 오류: {e}")
                continue
        
        print(f"\n총 {len(all_news)}개 뉴스 수집 완료")
        
    except Exception as e:
        print(f"구글 뉴스 수집 오류: {e}")
    
    return all_news[:15]  # 최대 15개

def summarize_and_deduplicate(news_list):
    """AI로 뉴스 요약 + 중복 제거 + 10개 선정"""
    if not news_list:
        return [], "수집된 뉴스가 없습니다."
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # 뉴스 텍스트 준비 (본문 포함)
        news_text = "\n\n" + "="*50 + "\n\n".join([
            f"기사 {i+1}\n출처: {news['site']}\n제목: {news['title']}\n본문: {news['content'][:800]}"
            for i, news in enumerate(news_list)
        ])
        
        # 1단계: 중복 제거 및 10개 선정
        print("AI 분석 중: 중복 제거 및 주요 뉴스 10개 선정...")
        
        selection_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """당신은 세무 전문가입니다.
제공된 뉴스들을 분석하여:
1. 내용이 중복되는 뉴스는 가장 상세한 1개만 선택
2. 실무적으로 중요한 순서대로 정확히 10개 선정
3. 선정된 기사 번호만 쉼표로 구분하여 출력 (예: 1,3,5,7,8,9,11,12,14,15)"""},
                {"role": "user", "content": f"""다음 뉴스들 중 중복을 제거하고 실무적으로 중요한 10개를 선정하세요.

{news_text}

출력 형식: 기사번호,기사번호,기사번호... (정확히 10개)"""}
            ],
            max_tokens=100,
            temperature=0.1
        )
        
        selected_indices_str = selection_response.choices[0].message.content.strip()
        print(f"선정된 기사: {selected_indices_str}")
        
        # 선정된 인덱스 파싱
        try:
            selected_indices = [int(x.strip())-1 for x in selected_indices_str.split(',')]
            selected_indices = [i for i in selected_indices if 0 <= i < len(news_list)][:10]
        except:
            selected_indices = list(range(min(10, len(news_list))))
        
        selected_news = [news_list[i] for i in selected_indices]
        
        # 2단계: 선정된 10개 뉴스 실무적으로 요약
        print("AI 분석 중: 실무적 요약 생성...")
        
        selected_text = "\n\n" + "="*50 + "\n\n".join([
            f"기사 {i+1}\n출처: {news['site']}\n제목: {news['title']}\n본문: {news['content'][:1000]}"
            for i, news in enumerate(selected_news)
        ])
        
        summary_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """당신은 15년 경력의 세무사입니다.
각 뉴스를 다음 관점에서 실무적으로 요약하세요:

1. 세목 명시: (소득세/법인세/부가세/상속세/증여세/양도세 중)
2. 핵심 변경사항: 무엇이 어떻게 바뀌는가
3. 적용 대상: 누구에게 영향을 주는가
4. 적용 시기: 언제부터 적용되는가
5. 실무 영향: 납세자/세무사가 주의할 점

각 뉴스당 3-4문장으로 구체적으로 작성.
금액, 세율, 날짜 등 수치는 반드시 포함.
전문용어는 괄호로 쉽게 설명."""},
                {"role": "user", "content": f"""다음 10개 뉴스를 실무 관점에서 요약하세요.

{selected_text}

형식:
1. [출처] (세목) 
   요약 내용 3-4문장"""}
            ],
            max_tokens=3000,
            temperature=0.1
        )
        
        summary = summary_response.choices[0].message.content
        
        return selected_news, summary
        
    except Exception as e:
        print(f"AI 분석 오류: {e}")
        return news_list[:10], "AI 요약을 생성할 수 없습니다."

def send_email(news_list, summary):
    """Gmail로 이메일 전송"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"📊 오늘의 주요 조세 뉴스 TOP 10 ({datetime.now().strftime('%Y-%m-%d')})"
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Malgun Gothic', Arial, sans-serif; line-height: 1.8; color: #333; }}
                .container {{ max-width: 900px; margin: 0 auto; background-color: white; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .summary {{ background-color: #f8f9fa; padding: 30px; margin: 20px; border-left: 5px solid #667eea; }}
                .summary h2 {{ margin-top: 0; color: #667eea; font-size: 20px; }}
                .summary-content {{ line-height: 2.0; white-space: pre-line; }}
                .news-list {{ padding: 20px; }}
                .news-item {{ margin: 20px 0; padding: 20px; background-color: #f8f9fa; border-radius: 8px; }}
                .news-source {{ display: inline-block; background-color: #667eea; color: white; padding: 5px 12px; border-radius: 15px; font-size: 13px; font-weight: bold; }}
                .news-title {{ font-size: 17px; font-weight: 600; color: #333; margin: 12px 0; }}
                .news-link {{ display: inline-block; margin-top: 10px; color: #667eea; text-decoration: none; font-weight: 600; }}
                .footer {{ margin-top: 30px; padding: 20px; border-top: 2px solid #ddd; text-align: center; color: #666; }}
                .badge {{ background-color: #ffc107; color: #000; padding: 5px 10px; border-radius: 5px; font-size: 12px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 오늘의 주요 조세 뉴스 TOP 10</h1>
                    <p>{datetime.now().strftime('%Y년 %m월 %d일 %A')}</p>
                    <p style="font-size:14px; opacity:0.9;">중복 제거 및 실무 중요도 순</p>
                </div>
                
                <div class="summary">
                    <h2>🎯 세무사 관점 실무 요약</h2>
                    <div class="summary-content">{summary}</div>
                </div>
                
                <div class="news-list">
                    <h2 style="color: #667eea;">📰 원문 링크</h2>
        """
        
        for i, news in enumerate(news_list, 1):
            html_content += f"""
                <div class="news-item">
                    <span class="news-source">{news['site']}</span>
                    <span class="badge">{news['keyword']}</span>
                    <div class="news-title">{i}. {news['title']}</div>
                    <a href="{news['link']}" class="news-link">📄 기사 원문 보기 →</a>
                </div>
            """
        
        html_content += """
                </div>
                <div class="footer">
                    <p><strong>매일 아침 7시 30분 자동 발송</strong></p>
                    <p>실무에 꼭 필要한 조세 뉴스만 엄선하여 전달합니다.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        print("이메일 전송 중...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        print("✅ 이메일 전송 성공!")
        return True
        
    except Exception as e:
        print(f"❌ 이메일 전송 오류: {e}")
        return False

def main():
    print("=" * 60)
    print(f"조세 뉴스 수집 시작: {datetime.now()}")
    print("=" * 60)
    
    # 1. 뉴스 수집 (본문 포함)
    news_list = scrape_google_news()
    
    if not news_list:
        print("\n⚠️ 수집된 뉴스가 없습니다.")
        send_email([], "오늘은 수집된 뉴스가 없습니다.")
        return
    
    print(f"\n✅ {len(news_list)}개 뉴스 수집 완료")
    
    # 2. AI 분석: 중복 제거 + 10개 선정 + 실무 요약
    selected_news, summary = summarize_and_deduplicate(news_list)
    
    print(f"\n✅ 최종 선정: {len(selected_news)}개")
    
    # 3. 이메일 전송
    print("\n📧 이메일 발송 중...")
    success = send_email(selected_news, summary)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ 작업 완료!")
        print("=" * 60)

if __name__ == "__main__":
    main()
