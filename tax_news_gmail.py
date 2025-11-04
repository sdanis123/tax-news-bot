import requests
from bs4 import BeautifulSoup
from datetime import datetime
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import xml.etree.ElementTree as ET

# 설정값 (환경변수로 설정 권장)
GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS', "YOUR_GMAIL@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', "YOUR_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', "YOUR_EMAIL@gmail.com")
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', "YOUR_OPENAI_API_KEY")

def scrape_google_news():
    """구글 뉴스에서 세금 관련 뉴스 수집 (특정 언론사만)"""
    all_news = []
    
    # 수집할 언론사 목록
    allowed_sources = [
        '한국세정신문',
        '조세일보',
        '세정일보',
        '세무사신문',
        '택스워치',
        '조세금융신문'
    ]
    
    # 검색할 키워드들
    keywords = ['세금', '조세', '국세청', '부가가치세', '법인세']
    
    try:
        print(f"구글 뉴스에서 세금 뉴스 수집 중... (대상: {', '.join(allowed_sources)})")
        
        for keyword in keywords:
            # 구글 뉴스 RSS 피드
            url = f"https://news.google.com/rss/search?q={keyword}+when:1d&hl=ko&gl=KR&ceid=KR:ko"
            
            try:
                response = requests.get(url, timeout=15)
                response.encoding = 'utf-8'
                
                # XML 파싱
                root = ET.fromstring(response.content)
                
                # 뉴스 아이템 찾기
                items = root.findall('.//item')
                
                for item in items:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    source_elem = item.find('source')
                    
                    if title_elem is not None and link_elem is not None:
                        title = title_elem.text
                        link = link_elem.text
                        source = source_elem.text if source_elem is not None else ''
                        
                        # 지정된 언론사만 필터링
                        if any(allowed in source for allowed in allowed_sources):
                            # 중복 체크
                            if not any(news['title'] == title for news in all_news):
                                all_news.append({
                                    'site': source,
                                    'title': title,
                                    'link': link
                                })
                                print(f"  ✓ [{source}] {title[:50]}")
                
            except Exception as e:
                print(f"  {keyword} 키워드 오류: {e}")
                continue
        
        print(f"\n총 {len(all_news)}개 뉴스 수집 완료")
        
    except Exception as e:
        print(f"구글 뉴스 수집 오류: {e}")
    
    return all_news

def summarize_with_ai(news_list):
    """OpenAI GPT로 뉴스 요약 (4o-mini 최적화)"""
    if not news_list:
        return "수집된 뉴스가 없습니다."
    
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # 뉴스 텍스트 준비
        news_text = "\n\n".join([
            f"{i+1}. [{news['site']}] {news['title']}"
            for i, news in enumerate(news_list)
        ])
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """당신은 세무 전문 뉴스 에디터입니다. 
각 뉴스 제목을 분석하여 다음 규칙으로 요약하세요:
1. 제목에서 핵심 키워드 파악 (세금 종류, 금액, 대상, 기간 등)
2. "누가 무엇을 어떻게" 형식으로 명확히 작성
3. 구체적인 수치나 날짜가 있으면 반드시 포함
4. 각 뉴스당 정확히 2문장으로 작성
5. 전문 용어는 괄호로 쉽게 설명

나쁜 예: "세법이 바뀐다는 내용입니다"
좋은 예: "국세청이 2025년부터 가상자산 소득세(암호화폐 거래 수익에 부과되는 세금) 과세를 2년 유예한다고 발표했다. 유예 기간 동안 과세 기준과 세율을 재검토할 예정이다." """}, 
                {"role": "user", "content": f"""다음 세금 뉴스 제목들을 요약해주세요.

{news_text}

형식:
번호. [출처] 첫 번째 문장. 두 번째 문장."""}
            ],
            max_tokens=2500,
            temperature=0.1  # 더 일관적인 결과
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI 요약 오류: {e}")
        return "AI 요약을 생성할 수 없습니다."

def send_email(news_list, summary):
    """Gmail로 이메일 전송"""
    try:
        # 이메일 구성
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"📊 오늘의 세금 뉴스 ({datetime.now().strftime('%Y-%m-%d')})"
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL
        
        # HTML 이메일 본문
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Malgun Gothic', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
                .summary {{ background-color: #f9f9f9; padding: 25px; margin: 20px; border-left: 4px solid #667eea; }}
                .summary h2 {{ margin-top: 0; color: #667eea; }}
                .news-list {{ padding: 20px; }}
                .news-item {{ margin: 15px 0; padding: 15px; border-bottom: 1px solid #eee; }}
                .news-source {{ display: inline-block; background-color: #667eea; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin-right: 10px; }}
                .news-title {{ font-size: 16px; font-weight: 500; color: #333; margin: 10px 0; }}
                .news-link {{ display: inline-block; margin-top: 8px; color: #667eea; text-decoration: none; font-weight: 500; }}
                .news-link:hover {{ text-decoration: underline; }}
                .footer {{ margin-top: 30px; padding: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; text-align: center; }}
                .count {{ background-color: #fff3cd; padding: 10px; margin: 20px; border-radius: 8px; text-align: center; color: #856404; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 오늘의 세금 뉴스</h1>
                    <p>{datetime.now().strftime('%Y년 %m월 %d일 %A')}</p>
                </div>
                
                <div class="count">
                    📰 오늘 수집된 뉴스: <strong>{len(news_list)}개</strong>
                </div>
                
                <div class="summary">
                    <h2>🤖 AI 요약</h2>
                    <p style="white-space: pre-line; line-height: 1.8;">{summary}</p>
                </div>
                
                <div class="news-list">
                    <h2 style="color: #667eea;">📰 전체 뉴스 목록</h2>
        """
        
        for i, news in enumerate(news_list, 1):
            html_content += f"""
                <div class="news-item">
                    <span class="news-source">{news['site']}</span>
                    <div class="news-title">{i}. {news['title']}</div>
                    <a href="{news['link']}" class="news-link">기사 원문 보기 →</a>
                </div>
            """
        
        html_content += """
                </div>
                
                <div class="footer">
                    <p>이 이메일은 자동으로 발송되었습니다.</p>
                    <p>매일 아침 최신 세금 뉴스를 받아보세요 📧</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # HTML 파트 추가
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Gmail SMTP 서버로 전송
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
    print("=" * 50)
    print(f"세금 뉴스 수집 시작: {datetime.now()}")
    print("=" * 50)
    
    # 1. 뉴스 스크래핑 (구글 뉴스 RSS)
    news_list = scrape_google_news()
    
    if not news_list:
        print("\n⚠️ 수집된 뉴스가 없습니다.")
        summary = "오늘은 뉴스를 수집하지 못했습니다."
        send_email([], summary)
        return
    
    print(f"\n✅ {len(news_list)}개 뉴스 수집 완료")
    
    # 2. AI 요약
    print("\n🤖 AI 요약 생성 중...")
    summary = summarize_with_ai(news_list)
    
    # 3. 이메일 전송
    print("\n📧 이메일 발송 중...")
    success = send_email(news_list, summary)
    
    if success:
        print("\n" + "=" * 50)
        print("✅ 작업 완료!")
        print("=" * 50)
    else:
        print("\n⚠️ 일부 작업에 실패했습니다.")

if __name__ == "__main__":
    main()
