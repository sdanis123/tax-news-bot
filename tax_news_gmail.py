import requests
from bs4 import BeautifulSoup
from datetime import datetime
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# 설정값 (환경변수로 설정 권장)
GMAIL_ADDRESS = "YOUR_GMAIL@gmail.com"  # 발신 Gmail 주소
GMAIL_APP_PASSWORD = "YOUR_APP_PASSWORD"  # Gmail 앱 비밀번호
RECIPIENT_EMAIL = "YOUR_EMAIL@gmail.com"  # 수신 이메일 (본인 이메일)
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"  # OpenAI API Key

def scrape_tax_news():
    """조세신문 최신 뉴스 스크래핑"""
    news_list = []
    
    try:
        # 조세신문 메인 페이지
        url = "https://www.joseilbo.com/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 뉴스 기사 찾기 (사이트 구조에 따라 조정 필요)
        articles = soup.select('.article-list li')[:5]  # 상위 5개
        
        for article in articles:
            try:
                title_elem = article.select_one('a')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    link = title_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = f"https://www.joseilbo.com{link}"
                    
                    # 기사 본문 가져오기
                    if link:
                        article_response = requests.get(link, headers=headers, timeout=10)
                        article_soup = BeautifulSoup(article_response.content, 'html.parser')
                        content_elem = article_soup.select_one('.article-body, .news-content, article')
                        content = content_elem.get_text(strip=True)[:1000] if content_elem else ""
                        
                        news_list.append({
                            'title': title,
                            'link': link,
                            'content': content
                        })
            except Exception as e:
                print(f"개별 기사 처리 오류: {e}")
                continue
                
    except Exception as e:
        print(f"스크래핑 오류: {e}")
    
    return news_list

def summarize_with_ai(news_list):
    """OpenAI GPT로 뉴스 요약"""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # 뉴스 텍스트 준비
        news_text = "\n\n".join([
            f"제목: {news['title']}\n내용: {news['content'][:500]}"
            for news in news_list
        ])
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 또는 "gpt-4o"
            messages=[
                {"role": "system", "content": "당신은 세금 뉴스를 요약하는 전문가입니다."},
                {"role": "user", "content": f"""다음은 오늘의 세금 관련 뉴스입니다. 각 뉴스를 2-3문장으로 핵심만 요약해주세요.

{news_text}

각 뉴스마다 번호를 붙이고, 핵심 내용만 간결하게 요약해주세요."""}
            ],
            max_tokens=1500,
            temperature=0.3
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI 요약 오류: {e}")
        return None

def send_email(news_list, summary):
    """Gmail로 이메일 전송"""
    try:
        # 이메일 구성
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"📊 오늘의 세금 뉴스 ({datetime.now().strftime('%Y-%m-%d')})"
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = RECIPIENT_EMAIL
        
        # HTML 이메일 본문 작성
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .summary {{ background-color: #f9f9f9; padding: 20px; margin: 20px 0; border-left: 4px solid #4CAF50; }}
                .news-item {{ margin: 20px 0; padding: 15px; border-bottom: 1px solid #ddd; }}
                .news-title {{ font-size: 16px; font-weight: bold; color: #2196F3; }}
                .news-link {{ display: inline-block; margin-top: 10px; color: #4CAF50; text-decoration: none; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 오늘의 세금 뉴스</h1>
                <p>{datetime.now().strftime('%Y년 %m월 %d일')}</p>
            </div>
            
            <div class="summary">
                <h2>🤖 AI 요약</h2>
                <p style="white-space: pre-line;">{summary if summary else "요약을 생성할 수 없습니다."}</p>
            </div>
            
            <div style="padding: 20px;">
                <h2>📰 원문 링크</h2>
        """
        
        for i, news in enumerate(news_list, 1):
            html_content += f"""
                <div class="news-item">
                    <div class="news-title">{i}. {news['title']}</div>
                    <a href="{news['link']}" class="news-link">기사 원문 보기 →</a>
                </div>
            """
        
        html_content += """
            </div>
            
            <div class="footer">
                <p>이 이메일은 자동으로 발송되었습니다.</p>
            </div>
        </body>
        </html>
        """
        
        # HTML 파트 추가
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Gmail SMTP 서버로 전송
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        print("이메일 전송 성공!")
        
    except Exception as e:
        print(f"이메일 전송 오류: {e}")

def main():
    print(f"세금 뉴스 수집 시작: {datetime.now()}")
    
    # 1. 뉴스 스크래핑
    news_list = scrape_tax_news()
    
    if not news_list:
        print("수집된 뉴스가 없습니다.")
        return
    
    print(f"{len(news_list)}개 뉴스 수집 완료")
    
    # 2. AI 요약
    summary = summarize_with_ai(news_list)
    
    # 3. 이메일 전송
    send_email(news_list, summary)
    
    print("작업 완료!")

if __name__ == "__main__":
    main()
