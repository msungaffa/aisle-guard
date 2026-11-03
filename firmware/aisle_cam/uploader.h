// Supabase aisle_events 전송. 별도 태스크(코어 0)에서 큐를 비우므로 판정 루프를 막지 않는다.
#pragma once

void uploader_begin();
// 이벤트 JSON 한 줄을 큐에 넣는다 (최근 20건 보관, 넘치면 가장 오래된 것을 버림)
void uploader_enqueue(const char *json);
int uploader_pending();
