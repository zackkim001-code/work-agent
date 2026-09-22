#!/usr/bin/env python3
"""낭독 대본 → 듣기 페이지(단일 HTML) 생성. 한국어 기본, 영어 대본이 있으면 언어 전환 버튼이 붙는다.

언어마다 두 가지 재생 경로가 있다.
  1) 자연 음성 (있을 때): make_audio.py 가 만든 mp3 를 아티팩트 보조 파일(audio/…mp3)로 참조하는 <audio>.
  2) 기기 음성 (항상): 브라우저 내장 음성(Web Speech API)으로 대본을 문장 단위로 읽는다. 언어별로 ko/en 음성만 목록에 올린다.
     mp3 가 있으면 접힌 '예비' 섹션으로 내려가고, mp3 를 불러오지 못하면 자동으로 펼친다.

외부 리소스를 전혀 쓰지 않는다. 대본·요약은 이스케이프한 일반 텍스트로만 삽입한다.
속도 기본 1.1배. 언어·속도·목소리 선택은 그 기기 브라우저에만 기억된다(localStorage) — 그래서 안정 URL 로 운영한다.

사용법:
  python make_listen_page.py --date 2026-09-22 --script-file ko.txt [--summary-file ko_sum.txt] \
      [--script-file-en en.txt] [--summary-file-en en_sum.txt] \
      --brief-url https://app.notion.com/p/... \
      [--audio "선히 (여성)=work/brief-sunhi.mp3" …] [--audio-en "Jenny (female)=work/brief-jenny.mp3" …] \
      [--audio-dir audio] --out listen.html [--manifest manifest.json]

  stdin JSON: {"date", "script", "summary", "script_en", "summary_en", "brief_url",
               "audio": [{"label","path"}], "audio_en": [{"label","path"}]}

검사 (실패 시 종료 코드 1): 대본 비어 있음/3000자 초과, 대본·요약에 URL, brief_url 이 https 아님, mp3 없음/14MB 초과.
종료 코드: 0 성공 / 1 검사 실패 / 2 사용법 오류
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import date as _date

for _s in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

MAX_SCRIPT = 3000
MAX_AUDIO_ONE = 14 * 1024 * 1024
URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
WEEKDAYS_KO = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+")
SOFT_LIMIT = 180

UI = {
    "ko": {"h1": "오늘 업무 브리핑", "natural": "미리 만들어 둔 자연 음성입니다. ▶ 를 누르면 바로 재생됩니다.",
           "voice": "목소리", "rate": "속도", "play": "▶ 들려주기", "pause": "⏸ 일시정지", "stop": "■ 정지",
           "resume": "▶ 이어듣기", "again": "▶ 다시 듣기",
           "tts_status": "재생을 누르면 이 기기의 음성으로 읽어 드립니다.",
           "fallback": "기기 음성으로 듣기 (자연 음성이 안 나올 때)",
           "audio_err": "자연 음성을 불러오지 못했습니다. 아래 기기 음성으로 들어 주세요.",
           "no_tts": "이 브라우저는 음성 읽기를 지원하지 않습니다. 아래 글을 읽어 주세요.",
           "no_voice": "이 언어 음성 없음 (기본 음성 사용)", "loading": "불러오는 중…",
           "hint_title": "목소리가 딱딱하게 들리면",
           "hint": ["이 섹션은 기기에 설치된 음성만 씁니다. 위 목록에 여러 개가 있으면 바꿔 들어 보세요. 선택은 이 기기에 기억됩니다.",
                    "iPhone: 설정 › 손쉬운 사용 › 콘텐츠 말하기 › 음성에서 내려받은 음성이 목록에 나타납니다. 내려받은 뒤 이 페이지를 새로 고치세요.",
                    "Android: 설정 › 접근성 › 텍스트 음성 변환 › Google 음성 서비스에서 음성을 내려받고 고품질을 고르세요.",
                    "PC: Edge 브라우저로 열면 자연스러운 온라인 음성이 목록에 나옵니다."],
           "done": "끝났습니다.", "stopped": "정지했습니다.", "paused": "일시정지", "prep": "준비 중…",
           "err": "음성 재생 오류", "voice_prefix": "음성: ", "press": " · 재생을 누르세요.", "online": " · 온라인",
           "foot1": "노션 브리핑 페이지 열기",
           "foot2": "이 페이지는 평일 아침마다 같은 주소에서 새 내용으로 바뀝니다. 즐겨찾기해 두면 카카오톡 없이도 열 수 있습니다.",
           "foot3": "음성이 나오지 않으면 위 글을 그대로 읽거나, 휴대폰의 화면 읽기 기능을 사용하세요."},
    "en": {"h1": "Today's work briefing", "natural": "Pre-rendered natural voice. Press ▶ to play.",
           "voice": "Voice", "rate": "Speed", "play": "▶ Play", "pause": "⏸ Pause", "stop": "■ Stop",
           "resume": "▶ Resume", "again": "▶ Play again",
           "tts_status": "Press play to hear this with your device's voice.",
           "fallback": "Device voice (if the natural voice does not load)",
           "audio_err": "Could not load the natural voice. Use the device voice below.",
           "no_tts": "This browser does not support speech. Please read the text below.",
           "no_voice": "No voice for this language (system default)", "loading": "Loading…",
           "hint_title": "If the voice sounds robotic",
           "hint": ["This section only uses voices installed on your device. Try another one from the list; the choice is remembered on this device.",
                    "iPhone: voices downloaded under Settings › Accessibility › Spoken Content › Voices appear in the list after a refresh.",
                    "Android: download a higher-quality voice under Settings › Accessibility › Text-to-speech › Google TTS.",
                    "PC: Microsoft Edge exposes natural online voices in the list."],
           "done": "Done.", "stopped": "Stopped.", "paused": "Paused", "prep": "Starting…",
           "err": "Speech error", "voice_prefix": "Voice: ", "press": " · press play.", "online": " · online",
           "foot1": "Open the Notion briefing page",
           "foot2": "This page is refreshed at the same address every weekday morning. Bookmark it to open it without KakaoTalk.",
           "foot3": "If there is no sound, read the text above or use your phone's screen reader."},
}


def date_long(s, lang):
    d = _date.fromisoformat(s)
    if lang == "en":
        return f"{WEEKDAYS_EN[d.weekday()]}, {MONTHS_EN[d.month - 1]} {d.day}, {d.year}"
    return f"{d.year}년 {d.month}월 {d.day}일 {WEEKDAYS_KO[d.weekday()]}"


def split_sentences(paragraph):
    out = []
    for sent in SENT_SPLIT.split(paragraph.strip()):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= SOFT_LIMIT:
            out.append(sent)
            continue
        buf = ""
        for piece in re.split(r"(?<=,)\s+", sent):
            if buf and len(buf) + len(piece) + 1 > SOFT_LIMIT:
                out.append(buf.strip())
                buf = piece
            else:
                buf = (buf + " " + piece).strip()
        if buf:
            out.append(buf.strip())
    return out


def script_to_html(script):
    paras = [p for p in re.split(r"\n\s*\n|\n", script.strip()) if p.strip()]
    parts = []
    for p in paras:
        spans = "".join(f'<span class="s">{html.escape(s)}</span> ' for s in split_sentences(p))
        parts.append(f"      <p>{spans.rstrip()}</p>")
    return "\n".join(parts)


RATE_OPTIONS = """<option value="0.9">0.9×</option><option value="1">1.0×</option><option value="1.1" selected>1.1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option>"""


def audio_block(lang, audio_specs, audio_dir, version):
    """→ (HTML, files 맵, 오류)."""
    if not audio_specs:
        return "", {}, []
    t = UI[lang]
    errs, opts, files = [], [], {}
    for label, path in audio_specs:
        if not os.path.isfile(path):
            errs.append(f"오디오 파일 없음: {path}")
            continue
        size = os.path.getsize(path)
        if size > MAX_AUDIO_ONE:
            errs.append(f"오디오 파일이 {MAX_AUDIO_ONE // 1048576}MB를 넘음: {path}")
            continue
        published = f"{audio_dir.strip('/')}/{os.path.basename(path)}" if audio_dir else os.path.basename(path)
        files[published] = os.path.abspath(path)
        src = f"{published}?v={version}"
        opts.append(f'<option value="{html.escape(label, quote=True)}" data-src="{html.escape(src, quote=True)}">{html.escape(label)}</option>')
    if errs or not opts:
        return "", {}, errs
    block = f"""    <section class="player" data-role="natural">
      <div class="row">
        <label>{t["voice"]}<select data-role="avoice">{"".join(opts)}</select></label>
        <label>{t["rate"]}<select data-role="arate">{RATE_OPTIONS}</select></label>
      </div>
      <audio data-role="audio" controls preload="auto"></audio>
      <p class="status" data-role="astatus">{t["natural"]}</p>
    </section>
"""
    return block, files, []


def tts_block(lang):
    t = UI[lang]
    hints = "".join(f"<li>{html.escape(h)}</li>" for h in t["hint"])
    return f"""    <section class="player" data-role="tts">
      <div class="row">
        <button data-role="play" class="primary" type="button">{t["play"]}</button>
        <button data-role="pause" type="button" disabled>{t["pause"]}</button>
        <button data-role="stop" type="button" disabled>{t["stop"]}</button>
      </div>
      <div class="row">
        <label>{t["rate"]}<select data-role="rate">{RATE_OPTIONS}</select></label>
        <label>{t["voice"]}<select data-role="voice"><option value="">{t["loading"]}</option></select></label>
      </div>
      <p class="status" data-role="status">{t["tts_status"]}</p>
      <details class="hint"><summary>{t["hint_title"]}</summary><ul>{hints}</ul></details>
    </section>
"""


def lang_block(lang, date_s, script, summary, audio_specs, audio_dir, version, brief_url, hidden):
    t = UI[lang]
    audio_html, files, errs = audio_block(lang, audio_specs, audio_dir, version)
    tts = tts_block(lang)
    if audio_html:
        tts = f'    <details class="fallback"><summary>{t["fallback"]}</summary>\n{tts}    </details>\n'
    summary_html = f'    <p class="summary">{html.escape(summary)}</p>\n' if summary else ""
    ui_json = html.escape(json.dumps({k: t[k] for k in ("resume", "again", "play", "done", "stopped", "paused", "prep",
                                                          "err", "voice_prefix", "press", "online", "no_voice",
                                                          "no_tts", "loading", "audio_err")}, ensure_ascii=False), quote=True)
    block = f"""  <div class="lang" data-lang="{lang}" data-ui="{ui_json}"{' hidden' if hidden else ''}>
    <p class="date">{html.escape(date_long(date_s, lang))}</p>
    <h1>{t["h1"]}</h1>
{summary_html}{audio_html}{tts}    <article class="script" data-role="script">
{script_to_html(script)}
    </article>
    <p class="foot">
      <a href="{html.escape(brief_url, quote=True)}">{t["foot1"]}</a><br>
      {t["foot2"]}<br>
      {t["foot3"]}
    </p>
  </div>
"""
    return block, files, errs


TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>브리핑 듣기</title>
<meta name="description" content="{{DATE_LONG}} 업무 브리핑 낭독 대본과 음성 재생">
<meta name="robots" content="noindex">
<style>
:root{--bg:#FCFCFB;--surface:#F3F2EE;--fg:#2E2C27;--muted:#6B6A63;--border:#E1E1DF;--accent:#C6613F;--accent-fg:#FCFCFB;--hl:#F5E6DF}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#17171A;--surface:#212125;--fg:#ECEAE4;--muted:#A8A69E;--border:#33333A;--accent:#E07A56;--accent-fg:#17171A;--hl:#3A2A23}}
:root[data-theme="dark"]{--bg:#17171A;--surface:#212125;--fg:#ECEAE4;--muted:#A8A69E;--border:#33333A;--accent:#E07A56;--accent-fg:#17171A;--hl:#3A2A23}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--fg);font:16px/1.75 -apple-system,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif;-webkit-text-size-adjust:100%}
main{max-width:640px;margin:0 auto;padding:20px 16px 48px}
.langbar{display:flex;justify-content:flex-end;margin-bottom:8px}
.langbar[hidden]{display:none}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.seg button{border:0;border-radius:0;min-height:36px;padding:6px 14px;font-size:14px;background:var(--bg);color:var(--muted)}
.seg button[aria-pressed="true"]{background:var(--fg);color:var(--bg)}
.date{color:var(--muted);font-size:14px;margin:0 0 4px}
h1{font-size:24px;line-height:1.3;margin:0 0 16px;font-weight:700}
.summary{white-space:pre-line;color:var(--muted);margin:0 0 20px;font-size:15px}
.player{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:24px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.row + .row{margin-top:12px}
audio{display:block;width:100%;margin-top:12px}
button{font:inherit;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--fg);padding:10px 16px;cursor:pointer;min-height:44px}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-fg);font-weight:600;padding:12px 22px;font-size:17px}
button:disabled{opacity:.5;cursor:default}
label{color:var(--muted);font-size:14px;display:inline-flex;align-items:center;gap:6px}
select{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--fg);min-height:44px;max-width:100%}
select[data-role="voice"],select[data-role="avoice"]{flex:1 1 200px;min-width:0}
.status{color:var(--muted);font-size:14px;margin:12px 0 0;min-height:1.5em}
details.hint{margin-top:12px;color:var(--muted);font-size:14px}
details.hint summary{cursor:pointer;color:var(--fg)}
details.hint ul{margin:8px 0 0;padding-left:20px}
details.hint li{margin:4px 0}
details.fallback{margin-bottom:24px;color:var(--muted);font-size:14px}
details.fallback summary{cursor:pointer;color:var(--fg);padding:8px 0}
details.fallback .player{margin-top:8px;margin-bottom:0}
.script p{margin:0 0 14px}
.script span.s{border-radius:4px;padding:1px 2px}
.script span.s.on{background:var(--hl)}
.foot{margin-top:32px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:14px}
a{color:var(--fg)}
.lang[hidden]{display:none}
</style>
</head>
<body>
<main>
  <div class="langbar"{{LANGBAR_HIDDEN}}>
    <div class="seg" role="group" aria-label="Language">
      <button type="button" data-setlang="ko" aria-pressed="true">한국어</button>
      <button type="button" data-setlang="en" aria-pressed="false">English</button>
    </div>
  </div>
{{LANG_BLOCKS}}
</main>
<script>
(function () {
  var LANG_KEY = 'brief-listen-lang';
  function lp(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function sp(k, v) { try { window.localStorage.setItem(k, v); } catch (e) {} }
  var players = [];

  function initLang(root) {
    var lang = root.getAttribute('data-lang');
    var T = JSON.parse(root.getAttribute('data-ui') || '{}');
    var q = function (role) { return root.querySelector('[data-role="' + role + '"]'); };
    var api = { lang: lang, stopAll: function () {} };
    var stops = [];

    // ── 자연 음성 ──
    var audio = q('audio'), fallback = root.querySelector('details.fallback');
    if (audio) {
      var vsel = q('avoice'), rsel = q('arate'), astatus = q('astatus');
      var AV = 'brief-listen-avoice-' + lang, AR = 'brief-listen-arate-' + lang;
      var sv = lp(AV);
      if (sv) { for (var i = 0; i < vsel.options.length; i++) { if (vsel.options[i].value === sv) { vsel.selectedIndex = i; break; } } }
      var sr = lp(AR);
      if (sr) { for (var j = 0; j < rsel.options.length; j++) { if (rsel.options[j].value === sr) { rsel.value = sr; break; } } }
      var applySrc = function () { var o = vsel.options[vsel.selectedIndex]; var s = o ? o.getAttribute('data-src') : null; if (s) { audio.src = s; } };
      var applyRate = function () { audio.playbackRate = parseFloat(rsel.value) || 1; };
      applySrc(); applyRate();
      audio.addEventListener('loadedmetadata', applyRate);
      audio.addEventListener('play', applyRate);
      audio.addEventListener('error', function () { if (astatus) { astatus.textContent = T.audio_err; } if (fallback) { fallback.open = true; } });
      vsel.addEventListener('change', function () {
        var t = audio.currentTime, was = !audio.paused;
        sp(AV, vsel.value); applySrc();
        audio.addEventListener('loadedmetadata', function h() {
          audio.removeEventListener('loadedmetadata', h);
          try { audio.currentTime = Math.min(t, audio.duration || t); } catch (e) {}
          applyRate();
          if (was) { var p = audio.play(); if (p && p.catch) { p.catch(function () {}); } }
        });
      });
      rsel.addEventListener('change', function () { applyRate(); sp(AR, rsel.value); });
      stops.push(function () { if (!audio.paused) { audio.pause(); } });
    }

    // ── 기기 음성 ──
    var synth = window.speechSynthesis;
    var playBtn = q('play'), pauseBtn = q('pause'), stopBtn = q('stop'), rateSel = q('rate'), voiceSel = q('voice'), statusEl = q('status');
    var spans = Array.prototype.slice.call(root.querySelectorAll('[data-role="script"] span.s'));
    var idx = 0, gen = 0, state = 'idle', voices = [], voice = null;
    var RK = 'brief-listen-rate-' + lang, VK = 'brief-listen-voice-' + lang;
    if (!synth || typeof SpeechSynthesisUtterance === 'undefined' || !spans.length) {
      playBtn.disabled = true; voiceSel.disabled = true; statusEl.textContent = T.no_tts;
      api.stopAll = function () { stops.forEach(function (f) { f(); }); };
      return api;
    }
    var PREFER = [/natural/i, /premium|프리미엄/i, /enhanced|향상/i, /google/i, /yuna|유나/i, /sora|소라/i, /samantha|ava|zoe|allison|evan|nathan|siri/i];
    var AVOID = [/heami/i, /espeak/i, /compact/i];
    function rank(v) { var n = v.name || '', r = 50; for (var i = 0; i < PREFER.length; i++) { if (PREFER[i].test(n)) { r = i; break; } } for (var j = 0; j < AVOID.length; j++) { if (AVOID[j].test(n)) { r += 100; } } return r; }
    function key(v) { return v.voiceURI || v.name; }
    function setStatus(t) { statusEl.textContent = t; }
    function refreshVoices() {
      var all = synth.getVoices() || [];
      voices = all.filter(function (v) { return (v.lang || '').toLowerCase().replace('_', '-').indexOf(lang) === 0; });
      voices.sort(function (a, b) { var d = rank(a) - rank(b); return d !== 0 ? d : (a.name || '').localeCompare(b.name || ''); });
      var saved = lp(VK), cur = voice ? key(voice) : null;
      voice = null; voiceSel.innerHTML = '';
      if (!voices.length) { var o = document.createElement('option'); o.value = ''; o.textContent = all.length ? T.no_voice : T.loading; voiceSel.appendChild(o); voiceSel.disabled = true; return; }
      voiceSel.disabled = false;
      for (var k = 0; k < voices.length; k++) {
        var v = voices[k], opt = document.createElement('option');
        opt.value = key(v); opt.textContent = v.name + (v.localService ? '' : T.online); voiceSel.appendChild(opt);
        if ((saved && key(v) === saved) || (!saved && cur && key(v) === cur)) { voice = v; }
      }
      if (!voice) { voice = voices[0]; }
      voiceSel.value = key(voice);
      if (state === 'idle') { setStatus(T.voice_prefix + voice.name + T.press); }
    }
    function progress() { return (idx + 1) + ' / ' + spans.length + (voice ? ' · ' + voice.name : ''); }
    function highlight(i) {
      for (var k = 0; k < spans.length; k++) { spans[k].classList.toggle('on', k === i); }
      if (i >= 0 && i < spans.length) { var r = spans[i].getBoundingClientRect(); if (r.top < 80 || r.bottom > window.innerHeight - 40) { spans[i].scrollIntoView({ block: 'center', behavior: 'smooth' }); } }
    }
    function updateButtons() {
      playBtn.textContent = state === 'paused' ? T.resume : (state === 'done' ? T.again : T.play);
      pauseBtn.disabled = state !== 'playing'; stopBtn.disabled = state === 'idle' || state === 'done';
    }
    function speakCurrent() {
      if (idx >= spans.length) { state = 'done'; highlight(-1); setStatus(T.done); updateButtons(); return; }
      var my = ++gen, u = new SpeechSynthesisUtterance(spans[idx].textContent);
      u.lang = lang === 'en' ? 'en-US' : 'ko-KR';
      if (voice) { u.voice = voice; }
      u.rate = parseFloat(rateSel.value) || 1; u.pitch = 1;
      u.onstart = function () { if (my !== gen) return; highlight(idx); setStatus(progress()); };
      u.onend = function () { if (my !== gen) return; idx += 1; speakCurrent(); };
      u.onerror = function (e) { if (my !== gen) return; if (e && (e.error === 'interrupted' || e.error === 'canceled')) return; state = 'idle'; updateButtons(); setStatus(T.err + ': ' + ((e && e.error) || '?')); };
      synth.speak(u);
    }
    function restart() { gen++; synth.cancel(); setTimeout(speakCurrent, 60); }
    function play() {
      players.forEach(function (p) { if (p !== api) { p.stopAll(); } });
      if (audio && !audio.paused) { audio.pause(); }
      if (state === 'paused') { synth.resume(); state = 'playing'; updateButtons(); setStatus(progress()); return; }
      if (state === 'done' || state === 'idle') { idx = 0; }
      gen++; synth.cancel(); state = 'playing'; updateButtons(); setStatus(T.prep);
      setTimeout(speakCurrent, 60);
    }
    function pause() { if (state !== 'playing') return; synth.pause(); state = 'paused'; updateButtons(); setStatus(T.paused); }
    function stop() { gen++; synth.cancel(); idx = 0; state = 'idle'; highlight(-1); updateButtons(); setStatus(T.stopped); }
    if (audio) { audio.addEventListener('play', function () { if (state === 'playing') { stop(); } players.forEach(function (p) { if (p !== api) { p.stopAll(); } }); }); }
    var savedRate = lp(RK);
    if (savedRate) { for (var i2 = 0; i2 < rateSel.options.length; i2++) { if (rateSel.options[i2].value === savedRate) { rateSel.value = savedRate; break; } } }
    rateSel.addEventListener('change', function () { sp(RK, rateSel.value); if (state === 'playing') { restart(); } });
    voiceSel.addEventListener('change', function () {
      for (var k = 0; k < voices.length; k++) { if (key(voices[k]) === voiceSel.value) { voice = voices[k]; break; } }
      sp(VK, voiceSel.value);
      if (state === 'playing') { restart(); } else if (voice) { setStatus(T.voice_prefix + voice.name + T.press); }
    });
    playBtn.addEventListener('click', play); pauseBtn.addEventListener('click', pause); stopBtn.addEventListener('click', stop);
    stops.push(function () { if (state === 'playing' || state === 'paused') { stop(); } });
    api.refreshVoices = refreshVoices;
    api.stopAll = function () { stops.forEach(function (f) { f(); }); };
    refreshVoices(); updateButtons();
    return api;
  }

  var roots = Array.prototype.slice.call(document.querySelectorAll('.lang'));
  roots.forEach(function (r) { players.push(initLang(r)); });
  function refreshAll() { players.forEach(function (p) { if (p.refreshVoices) { p.refreshVoices(); } }); }
  if (window.speechSynthesis) {
    if (typeof speechSynthesis.addEventListener === 'function') { speechSynthesis.addEventListener('voiceschanged', refreshAll); }
    else if ('onvoiceschanged' in speechSynthesis) { speechSynthesis.onvoiceschanged = refreshAll; }
    setTimeout(refreshAll, 800);
  }
  window.addEventListener('pagehide', function () { if (window.speechSynthesis) { speechSynthesis.cancel(); } });

  // ── 언어 전환 ──
  var btns = Array.prototype.slice.call(document.querySelectorAll('[data-setlang]'));
  function setLang(l, remember) {
    if (!document.querySelector('.lang[data-lang="' + l + '"]')) { l = 'ko'; }
    players.forEach(function (p) { p.stopAll(); });
    roots.forEach(function (r) { r.hidden = r.getAttribute('data-lang') !== l; });
    btns.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-setlang') === l ? 'true' : 'false'); });
    document.documentElement.lang = l === 'en' ? 'en' : 'ko';
    if (remember) { sp(LANG_KEY, l); }
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { setLang(b.getAttribute('data-setlang'), true); }); });
  if (btns.length) { setLang(lp(LANG_KEY) || 'ko', false); }
})();
</script>
</body>
</html>
"""


def build(date_s, brief_url, ko, en, audio_dir="audio"):
    """ko/en: dict(script, summary, audio=[(label, path)]). en 은 None 가능. → (html, files, errs)."""
    errs = []
    for lang, d in (("ko", ko), ("en", en)):
        if d is None:
            continue
        s = (d.get("script") or "").strip()
        if not s:
            errs.append(f"[{lang}] 대본이 비어 있음")
        if len(s) > MAX_SCRIPT:
            errs.append(f"[{lang}] 대본이 {MAX_SCRIPT}자를 넘음 ({len(s)}자)")
        if URL_RE.search(s) or URL_RE.search(d.get("summary") or ""):
            errs.append(f"[{lang}] 대본·요약에 URL이 있음 (송출 규칙 위반)")
    if not (brief_url or "").startswith("https://"):
        errs.append("brief_url 은 https:// 로 시작해야 함")
    try:
        date_long(date_s, "ko")
        version = date_s.replace("-", "")
    except Exception:
        errs.append(f"날짜 형식 오류 (YYYY-MM-DD): {date_s}")
        version = "0"
    if errs:
        return None, {}, errs
    blocks, files = [], {}
    for lang, d, hidden in (("ko", ko, False), ("en", en, True)):
        if d is None:
            continue
        b, f, e = lang_block(lang, date_s, d.get("script", ""), (d.get("summary") or "").strip(),
                             d.get("audio") or [], audio_dir, version, brief_url, hidden)
        errs.extend(e)
        blocks.append(b)
        files.update(f)
    if errs:
        return None, {}, errs
    out = (TEMPLATE
           .replace("{{DATE_LONG}}", html.escape(date_long(date_s, "ko")))
           .replace("{{LANGBAR_HIDDEN}}", "" if en else " hidden")
           .replace("{{LANG_BLOCKS}}", "".join(blocks)))
    return out, files, []


def parse_audio_arg(s):
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"--audio 형식은 '라벨=경로': {s}")
    label, path = s.split("=", 1)
    return label.strip(), path.strip()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--script-file")
    ap.add_argument("--summary-file")
    ap.add_argument("--script-file-en")
    ap.add_argument("--summary-file-en")
    ap.add_argument("--brief-url")
    ap.add_argument("--audio", action="append", type=parse_audio_arg, default=[])
    ap.add_argument("--audio-en", action="append", type=parse_audio_arg, default=[])
    ap.add_argument("--audio-dir", default="audio")
    ap.add_argument("--out")
    ap.add_argument("--manifest")
    a = ap.parse_args()

    if a.date or a.script_file or a.brief_url:
        if not (a.date and a.script_file and a.brief_url):
            print("--date, --script-file, --brief-url 모두 필요 (또는 stdin JSON)", file=sys.stderr)
            return 2
        ko = {"script": read(a.script_file), "summary": read(a.summary_file) if a.summary_file else "", "audio": a.audio}
        en = None
        if a.script_file_en:
            en = {"script": read(a.script_file_en), "summary": read(a.summary_file_en) if a.summary_file_en else "",
                  "audio": a.audio_en}
        date_s, brief_url = a.date, a.brief_url
    else:
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"stdin JSON 파싱 실패: {e}", file=sys.stderr)
            return 2
        date_s, brief_url = data.get("date", ""), data.get("brief_url", "")
        ko = {"script": data.get("script", ""), "summary": data.get("summary", ""),
              "audio": [(x.get("label", ""), x.get("path", "")) for x in data.get("audio", [])]}
        en = None
        if data.get("script_en"):
            en = {"script": data.get("script_en", ""), "summary": data.get("summary_en", ""),
                  "audio": [(x.get("label", ""), x.get("path", "")) for x in data.get("audio_en", [])]}

    page, files, errs = build(date_s, brief_url, ko, en, a.audio_dir)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    if a.manifest:
        with open(a.manifest, "w", encoding="utf-8") as f:
            json.dump({"page": os.path.abspath(a.out) if a.out else None, "files": files,
                       "audio_count": len(files), "languages": ["ko"] + (["en"] if en else [])},
                      f, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(page)
        n = len(re.findall(r'<span class="s">', page))
        print(f"OK: {a.out} ({n}문장, 언어 {'ko+en' if en else 'ko'}, 자연 음성 {len(files)}개, {len(page)}바이트)")
        if files:
            print("files: " + json.dumps(files, ensure_ascii=False))
    else:
        sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
