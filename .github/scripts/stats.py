import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

OUT = pathlib.Path(__file__).resolve().parents[2] / "stats.svg"
KST = dt.timezone(dt.timedelta(hours=9))
BANDS = [("Morning", 6, 14, "#F6E7C1"), ("Afternoon", 14, 22, "#E2C079"), ("Night", 22, 6, "#6F86C6")]
INK, MUTED, FAINT, LINE = "#EEEAE0", "#9AA2B4", "#6E7891", "#24314F"


def times_from_git(path):
    out = subprocess.run(["git", "-C", path, "log", "HEAD", "--format=%aI"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [dt.datetime.fromisoformat(x) for x in out.split()]


def times_from_github(repo, token):
    times, page = [], 1
    while True:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits?per_page=100&page={page}",
                                     headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                                              "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "profile-stats"})
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.load(r)
        times += [dt.datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00")) for c in items]
        if len(items) < 100:
            return times
        page += 1


def band_of(hour):
    for i, (_, a, b, _) in enumerate(BANDS):
        if (a <= hour < b) if a < b else (hour >= a or hour < b):
            return i


def stats(times):
    times = [t.astimezone(KST) for t in times]
    bands = [0] * len(BANDS)
    for t in times:
        bands[band_of(t.hour)] += 1
    return {"total": len(times), "bands": bands, "last": max(times) if times else None}


def svg(rows):
    W, top, rh = 640, 104, 56
    H = top + rh * len(rows) + 14
    BX, BW = 214, 280
    latest = max((s["last"] for _, s in rows if s["last"]), default=None)
    stamp = f"as of {latest:%Y-%m-%d}" if latest else ""
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Commit activity by project">',
         '<defs><linearGradient id="bg" x1="0" y1="0" x2="0.3" y2="1"><stop offset="0" stop-color="#070B17"/><stop offset="1" stop-color="#16244A"/></linearGradient></defs>',
         f'<rect width="{W}" height="{H}" rx="14" fill="url(#bg)"/>',
         f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{LINE}"/>',
         '<style>text{font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif}.m{font-family:"JetBrains Mono",Consolas,monospace}</style>',
         f'<text x="28" y="40" font-size="17" font-weight="700" fill="{INK}">Commit Activity</text>',
         f'<text x="{W - 28}" y="40" font-size="12" fill="{FAINT}" text-anchor="end" class="m">{stamp}</text>']
    x = 28
    for name, a, b, color in BANDS:
        label = f"{name} {a}–{b}h"
        p.append(f'<rect x="{x}" y="58" width="10" height="10" rx="2" fill="{color}"/>')
        p.append(f'<text x="{x + 16}" y="67" font-size="12" fill="{MUTED}">{label}</text>')
        x += 16 + len(label) * 7 + 22
    p += [f'<text x="28" y="92" font-size="11" fill="{FAINT}">Project</text>',
          f'<text x="196" y="92" font-size="11" fill="{FAINT}" text-anchor="end">Commits</text>',
          f'<text x="{BX}" y="92" font-size="11" fill="{FAINT}">Time of day</text>',
          f'<text x="{W - 28}" y="92" font-size="11" fill="{FAINT}" text-anchor="end">Last commit</text>']
    for i, (name, s) in enumerate(rows):
        y = top + i * rh
        p.append(f'<line x1="28" y1="{y}" x2="{W - 28}" y2="{y}" stroke="{LINE}"/>')
        cy = y + rh / 2 + 5
        p.append(f'<text x="28" y="{cy:.0f}" font-size="15" font-weight="600" fill="{INK}" class="m">{name}</text>')
        p.append(f'<text x="196" y="{cy:.0f}" font-size="15" font-weight="600" fill="{INK}" text-anchor="end">{s["total"]:,}</text>')
        bx = BX
        for k, (_, _, _, color) in enumerate(BANDS):
            share = s["bands"][k] / s["total"] if s["total"] else 0
            w = BW * share
            if w >= .5:
                p.append(f'<rect x="{bx:.1f}" y="{cy - 13:.0f}" width="{w:.1f}" height="12" fill="{color}"/>')
            if share >= .12:
                p.append(f'<text x="{bx + w / 2:.1f}" y="{cy + 14:.0f}" font-size="11" fill="{MUTED}" text-anchor="middle">{share * 100:.0f}%</text>')
            bx += w
        last = f'{s["last"]:%Y-%m-%d}' if s["last"] else "-"
        p.append(f'<text x="{W - 28}" y="{cy:.0f}" font-size="13" fill="{MUTED}" text-anchor="end" class="m">{last}</text>')
    p.append("</svg>")
    return "\n".join(p) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    spec, token = os.environ.get("STATS_REPOS", ""), os.environ.get("STATS_TOKEN", "")
    if not spec.strip():
        print("STATS_REPOS 비밀값이 아직 없어 이번에는 건너뜁니다")
        return
    rows = []
    for item in filter(None, (x.strip() for x in spec.split(";"))):
        name, src = (x.strip() for x in item.split("=", 1))
        try:
            times = times_from_git(src) if os.path.isdir(src) else times_from_github(src, token)
        except Exception as e:
            sys.exit(f"{name}: 커밋 기록을 읽지 못했습니다 ({type(e).__name__})")
        rows.append((name, stats(times)))
        print(f"{name}: 커밋 {rows[-1][1]['total']}")
    OUT.write_text(svg(rows), encoding="utf-8")
    print("stats.svg 를 만들었습니다")


if __name__ == "__main__":
    main()
