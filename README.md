# Microsoft Kakao News Bot

개인용 Microsoft 뉴스 카카오톡 브린핑 복입 복입이나라는. Google News RSS에서 Microsoft 관련 뉴스를 모아서, 한국어 요약을 만듭 드 Kakao Developers의 `나에게 본이기` API로 전송합니다.

## 1. Kakao 앱 준비

1. [Kakao Developers](https://developers.kakao.com/)에서 애플리케이션을 만듭니다.
2. 애플의 `REST API 키`를 확인합니다.
3. 카카오 로그인 Redirect URI에 `http://localhost`를 등록합니다.
4. 동의항목에서 카카오톡 메시지 전송 권한인 `talk_message`를 설정합니다.

## 2. 환경 파일 만듭기

`config.example.env`를 `.env`로 복사하고 값을 채워넣습니다.

```
powershell
Copy-Item config.example.env .env
```

## 3. Kakao refresh token 받기

```
powershell
$env:KAKAO_REST_API_KEY="카카오_REST_API_키"
python get_kakao_refresh_token.py
```

카카오 로그인의 Client Secret 기능을 켜두는 경우에는 아래 값도 설정합니다.

```
powershell
$env:KAKAO_CLIENT_SECRET="카카오_CLIENT_SECRET"
```

브라우저에서 승인 후 redirect URL에 붙은 `code` 값을 터미널에 입력합니다. 출력된 `KAKAO_REFRESH_TOKEN` 값을 `.env`에 넣습니다.

## 4. 테스트 실행

카카오톡 발송 없이 브리핑만 확인:

```
powershell
python ms_kakao_news_bot.py --dry-run
```

카카오톡 나에게 보낼:

```
powershell
python ms_kakao_news_bot.py
```

실행할 때마다 `site/msft-report.html`이 갱신됩니다. PC에서 아래 주소로 같은 리포트 페이지를 계속 열 수 있습니다.

```
text
http://localhost:8765/msft-report.html
```

## 5. OpenAI 요약 사용

`.env`에 `OPENAI_API_KEY`를 넣으면 귀칭 기반 요약 대신 OpenAI 요약을 사용합니다.

```
env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
```

## 6. Windows 작업 스케주버 예시

매일 오전 9시에 실행하려면 PowerShell에서 아래처럼 등록할 수 있습니다. 경로는 본인 환경에 맞춰 유지하세요.

```
powershell
$botDir = "C:\\Users\\jade6\\Documents\\Codex\\2026-06-03\\new-chat-2\\outputs\\ms-kakao-news-bot"
$action = New-ScheduledTaskAction -Execute "python" -Argument "ms_kakao_news_bot.py" -WorkingDirectory $botDir
$trigger = New-ScheduledTaskTrigger -Daily -At 9:00
Register-ScheduledTask -TaskName "Microsoft Kakao News Bot" -Action $action -Trigger $trigger -Description "Send Microsoft news briefing to KakaoTalk"
```

## 처한

- `나에게 본이기`는 개인용 브리핑에 적합합니다.
- 카카오톡 친구/다수 사용자에게 보낼려면 별도 권한과 서비스 사용자 조건이 필요합니다.
- 기사 본문 전체를 꺄짙지 않고 RSS 제목/요약/리크를 사용하문으로 구조가 다신합니다.
