// 이 파일을 같은 폴더에 secrets.h로 복사해서 값을 채운다. secrets.h는 커밋하지 않는다(gitignore).
#pragma once

// 2.4GHz Wi-Fi (ESP32는 5GHz에 붙지 못한다)
#define WIFI_SSID "your-ssid"
#define WIFI_PASSWORD "your-password"

// Supabase 프로젝트 (Settings → API). anon 키는 RLS로 aisle_events insert만 허용한다
#define SUPABASE_URL "https://xxxx.supabase.co"
#define SUPABASE_ANON_KEY "your-anon-key"

// 보드 이름 (aisle_events.device_id)
#define DEVICE_ID "aisle-cam-01"
