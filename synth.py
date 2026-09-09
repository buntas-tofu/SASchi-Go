#!/usr/bin/env python3
"""synth.py : program-level synthesis across characterized families.

Once executable SAS is locked down we manufacture self-contained programs that
exercise the characterized families, edge cases by construction, and gate each
against three oracles:

  rung 1  cross-language agreement    (Python draft == R draft)        breadth
  rung 2  our sas_semantics reference (both == the documented truth)   ground truth
  rung 3  licensed live SAS           (both == real SAS output)       last mile

Rung 1 alone shares blind spots: two translations making the SAME wrong
assumption agree and we never learn (the ROUND family, where every host banks
half-to-even). Rung 2, our reference, is the ground truth that catches them. Some
families instead break rung 1 directly (missing-comparison: Python naive reads
NaN<0 as False, R naive reads NA<0 as NA: the naive drafts disagree with each
other). Each program is also emitted as SAS with its expected table, staged for a
live-SAS capture before the license lapses.

The signal we hunt: a family where the FAITHFUL translation diverges from the
reference or across languages. That is a gap in our characterization, a quirk
still hiding. Deterministic and seeded; the generator is the point.
"""
import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sas_semantics import (is_sas_missing, sas_max, sas_round,  # noqa: E402
                           sas_intck, sas_date, date_to_sas, sas_proc_sort,
                           sas_num)

PY = os.environ.get("ROSETTA_PYTHON", sys.executable)
RSCRIPT = os.environ.get("ROSETTA_RSCRIPT") or shutil.which("Rscript") or "Rscript"
TB = os.environ.get("ROSETTA_TESTBED", "rosetta_testbed")
SYNTH_OUT = TB + "/telemetry/synth"
TOL = 1e-6


# ---- embedding helpers ----------------------------------------------------
def pv(x):
    return "float('nan')" if is_sas_missing(x) else repr(float(x))


def rv(x):
    return "NA_real_" if is_sas_missing(x) else repr(float(x))


def pylist(xs):
    return "[" + ", ".join(pv(x) for x in xs) + "]"


def rvec(xs):
    return "c(" + ", ".join(rv(x) for x in xs) + ")"


def sasnum(x):
    return "." if is_sas_missing(x) else f"{float(x):g}"


# ---- run and compare ------------------------------------------------------
def run_prog(lang, code, wd):
    fn = "d.py" if lang == "py" else "d.R"
    (wd / fn).write_text(code)
    cmd = [PY, str(wd / fn)] if lang == "py" else [str(RSCRIPT), str(wd / fn)]
    try:
        r = subprocess.run(cmd, cwd=wd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    f = wd / "results.feather"
    if r.returncode != 0 or not f.exists():
        return None, (r.stderr or "no feather")[-400:]
    import pandas as pd
    df = pd.read_feather(f)
    return {c: df[c].tolist() for c in df.columns}, None


def col_eq(a, b):
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        xm = x is None or (isinstance(x, float) and x != x)
        ym = y is None or (isinstance(y, float) and y != y)
        if xm or ym:
            if xm != ym:
                return False
        elif isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if abs(x - y) > TOL:
                return False
        elif str(x) != str(y):
            return False
    return True


def frames_equal(a, b):
    if a is None or b is None or set(a) != set(b):
        return False
    return all(col_eq(a[k], b[k]) for k in a)


# ---- families -------------------------------------------------------------
# round: half away from zero vs the host banker's round(). naive drafts AGREE
# with each other and both miss the odd-half boundaries: rung 2 catches.
def round_gen(rng):
    u = rng.choice([10.0, 50.0, 100.0])
    half = u / 2.0
    xs = [k * u + half for k in range(-3, 4)]
    xs += [rng.uniform(-5 * u, 5 * u) for _ in range(8)] + [0.0, None, None]
    rng.shuffle(xs)
    return {"u": u, "x": xs[:rng.randint(10, 16)]}


def round_exp(s):
    return {"x": [None if is_sas_missing(x) else float(x) for x in s["x"]],
            "rx": [None if is_sas_missing(x) else sas_round(float(x), s["u"]) for x in s["x"]]}


def round_py(s, naive):
    u = s["u"]
    core = (f"rx=[float('nan') if x!=x else round(x/{u})*{u} for x in X]" if naive else
            f"rx=[float('nan') if x!=x else math.copysign(math.floor(abs(x)/{u}+0.5+1e-9)*{u},x) for x in X]")
    return f"import math\nimport pandas as pd\nX={pylist(s['x'])}\n{core}\npd.DataFrame({{'x':X,'rx':rx}}).to_feather('results.feather')\n"


def round_r(s, naive):
    u = s["u"]
    core = (f"rx<-round(X/{u})*{u}" if naive else
            f"rx<-ifelse(is.na(X),NA_real_,sign(X)*floor(abs(X)/{u}+0.5+1e-9)*{u})")
    return f"suppressMessages(library(arrow))\nX<-{rvec(s['x'])}\n{core}\nwrite_feather(data.frame(x=X,rx=rx),'results.feather')\n"


def round_sas(s):
    lines = "\n".join(sasnum(x) for x in s["x"])
    return f"data w;\n input x;\n rx=round(x,{s['u']:g});\n datalines;\n{lines}\n;\nrun;\nproc print;run;\n"


# missing_compare: SAS missing sorts below every number, so (x<0) is TRUE for
# missing. Python naive NaN<0 is False; R naive NA<0 is NA. The naive drafts
# DISAGREE with each other: rung 1 catches directly.
def mc_gen(rng):
    xs = [rng.choice([-3.0, -1.0, -0.5, 0.0, 1.0, 2.5, None]) for _ in range(rng.randint(9, 14))]
    xs += [None, -1.0, 0.0]
    rng.shuffle(xs)
    return {"x": xs}


def mc_exp(s):
    return {"x": [None if is_sas_missing(x) else float(x) for x in s["x"]],
            "flag": [1 if (is_sas_missing(x) or float(x) < 0) else 0 for x in s["x"]]}


def mc_py(s, naive):
    core = ("flag=[(1 if x<0 else 0) for x in X]" if naive else
            "flag=[(1 if (x!=x or x<0) else 0) for x in X]")
    return f"import pandas as pd\nX={pylist(s['x'])}\n{core}\npd.DataFrame({{'x':X,'flag':flag}}).to_feather('results.feather')\n"


def mc_r(s, naive):
    expr = "as.integer(X<0)" if naive else "ifelse(is.na(X)|X<0,1L,0L)"
    return f"suppressMessages(library(arrow))\nX<-{rvec(s['x'])}\nflag<-{expr}\nwrite_feather(data.frame(x=X,flag=flag),'results.feather')\n"


def mc_sas(s):
    lines = "\n".join(sasnum(x) for x in s["x"])
    return f"data w;\n input x;\n flag=(x<0);\n datalines;\n{lines}\n;\nrun;\nproc print;run;\n"


# max_ignore_missing: SAS max() drops missings; all-missing is missing. Python
# naive np.max propagates NaN; R naive pmax without na.rm returns NA.
def mx_gen(rng):
    def v():
        return rng.choice([None, -2.0, 0.0, 1.0, 3.5, 7.0])
    rows = [(v(), v(), v()) for _ in range(rng.randint(10, 14))]
    rows.append((None, None, None))
    return {"rows": rows}


def mx_cols(s):
    return ([r[0] for r in s["rows"]], [r[1] for r in s["rows"]], [r[2] for r in s["rows"]])


def mx_exp(s):
    a, b, c = mx_cols(s)
    m = [sas_max(*r) for r in s["rows"]]
    f = lambda xs: [None if is_sas_missing(x) else float(x) for x in xs]
    return {"a": f(a), "b": f(b), "c": f(c),
            "m": [None if x is None else float(x) for x in m]}


def mx_py(s, naive):
    a, b, c = mx_cols(s)
    if naive:
        core = "import numpy as np\nm=[float(np.max([x,y,z])) for x,y,z in zip(A,B,C)]"
    else:
        core = ("def mx(*v):\n vv=[t for t in v if t==t]\n return max(vv) if vv else float('nan')\n"
                "m=[mx(x,y,z) for x,y,z in zip(A,B,C)]")
    return (f"import pandas as pd\nA={pylist(a)}\nB={pylist(b)}\nC={pylist(c)}\n{core}\n"
            "pd.DataFrame({'a':A,'b':B,'c':C,'m':m}).to_feather('results.feather')\n")


def mx_r(s, naive):
    a, b, c = mx_cols(s)
    core = ("m<-pmax(A,B,C)" if naive else
            "m<-pmax(A,B,C,na.rm=TRUE)\nm[!is.finite(m)]<-NA_real_")
    return (f"suppressMessages(library(arrow))\nA<-{rvec(a)}\nB<-{rvec(b)}\nC<-{rvec(c)}\n{core}\n"
            "write_feather(data.frame(a=A,b=B,c=C,m=m),'results.feather')\n")


def mx_sas(s):
    lines = "\n".join(f"{sasnum(a)} {sasnum(b)} {sasnum(c)}" for a, b, c in s["rows"])
    return f"data w;\n input a b c;\n m=max(a,b,c);\n datalines;\n{lines}\n;\nrun;\nproc print;run;\n"


# intck_year: SAS INTCK counts interval BOUNDARIES crossed (year(d2)-year(d1)),
# not elapsed time. Naive elapsed-year drafts AGREE with each other and both miss
# the boundary crossings under a year: rung 2 catches.
def ic_gen(rng):
    pairs = []
    for _ in range(rng.randint(8, 12)):
        d1 = date_to_sas(datetime.date(rng.randint(1990, 2018),
                                       rng.randint(1, 12), rng.randint(1, 28)))
        pairs.append((d1, d1 + rng.randint(-40, 430)))
    y = rng.randint(1990, 2018)               # guarantee a year-boundary crossing
    pairs.append((date_to_sas(datetime.date(y, 12, rng.randint(10, 28))),
                  date_to_sas(datetime.date(y + 1, 1, rng.randint(1, 20)))))
    return {"pairs": pairs}


def ic_exp(s):
    return {"d1": [float(a) for a, _ in s["pairs"]],
            "d2": [float(b) for _, b in s["pairs"]],
            "n": [float(sas_intck("YEAR", sas_date(a), sas_date(b))) for a, b in s["pairs"]]}


def ic_py(s, naive):
    d1 = [a for a, _ in s["pairs"]]
    d2 = [b for _, b in s["pairs"]]
    core = ("import math\nn=[float(math.floor((b-a)/365.25)) for a,b in zip(D1,D2)]" if naive else
            "import datetime\nE=datetime.date(1960,1,1)\n"
            "yr=lambda k:(E+datetime.timedelta(days=int(k))).year\n"
            "n=[float(yr(b)-yr(a)) for a,b in zip(D1,D2)]")
    return (f"import pandas as pd\nD1={d1!r}\nD2={d2!r}\n{core}\n"
            "pd.DataFrame({'d1':[float(x) for x in D1],'d2':[float(x) for x in D2],'n':n})"
            ".to_feather('results.feather')\n")


def ic_r(s, naive):
    d1 = "c(" + ",".join(str(a) for a, _ in s["pairs"]) + ")"
    d2 = "c(" + ",".join(str(b) for _, b in s["pairs"]) + ")"
    core = ("n<-floor((D2-D1)/365.25)" if naive else
            "yr<-function(k) as.integer(format(as.Date(k,origin='1960-01-01'),'%Y'))\n"
            "n<-as.numeric(yr(D2)-yr(D1))")
    return (f"suppressMessages(library(arrow))\nD1<-{d1}\nD2<-{d2}\n{core}\n"
            "write_feather(data.frame(d1=as.numeric(D1),d2=as.numeric(D2),n=as.numeric(n)),"
            "'results.feather')\n")


def ic_sas(s):
    lines = "\n".join(f"{a} {b}" for a, b in s["pairs"])
    return f"data w;\n input d1 d2;\n n=intck('YEAR',d1,d2);\n datalines;\n{lines}\n;\nrun;\nproc print;run;\n"


# sort_missing_first: SAS sorts missing BELOW every number. Naive pandas/R sort
# put missing last, agreeing with each other and both wrong: rung 2 catches.
def st_gen(rng):
    n = rng.randint(6, 11)
    rows = [{"i": i, "x": rng.choice([None, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0])}
            for i in range(n)]
    im, iv = rng.sample(range(n), 2)          # guarantee a missing AND a present
    rows[im]["x"] = None
    rows[iv]["x"] = rng.choice([-1.0, 0.0, 2.0])
    return {"rows": rows}


def st_exp(s):
    ordered = sas_proc_sort([dict(r) for r in s["rows"]], ["x"])
    return {"oi": [float(r["i"]) for r in ordered],
            "ox": [None if is_sas_missing(r["x"]) else float(r["x"]) for r in ordered]}


def st_py(s, naive):
    I = [r["i"] for r in s["rows"]]
    X = pylist([r["x"] for r in s["rows"]])
    core = ("d=pd.DataFrame({'i':I,'x':X}).sort_values('x',kind='stable')" if naive else
            "rows=sorted(zip(I,X),key=lambda t:(0 if t[1]!=t[1] else 1, t[1] if t[1]==t[1] else 0))\n"
            "d=pd.DataFrame({'i':[t[0] for t in rows],'x':[t[1] for t in rows]})")
    return (f"import pandas as pd\nI={I!r}\nX={X}\n{core}\n"
            "pd.DataFrame({'oi':[float(v) for v in d['i']],'ox':list(d['x'])})"
            ".to_feather('results.feather')\n")


def st_r(s, naive):
    I = "c(" + ",".join(str(r["i"]) for r in s["rows"]) + ")"
    X = rvec([r["x"] for r in s["rows"]])
    core = "o<-order(X)" if naive else "o<-order(!is.na(X),X)"
    return (f"suppressMessages(library(arrow))\nI<-{I}\nX<-{X}\n{core}\n"
            "write_feather(data.frame(oi=as.numeric(I[o]),ox=X[o]),'results.feather')\n")


def st_sas(s):
    lines = "\n".join(f"{r['i']} {sasnum(r['x'])}" for r in s["rows"])
    return (f"data w;\n input i x;\n datalines;\n{lines}\n;\nrun;\n"
            "proc sort data=w out=o;\n by x;\nrun;\nproc print data=o;run;\n")


# numeric_precision: SAS numeric is an IEEE double, so integers above 2**53
# collapse (round to even) and +1 becomes a no-op. Python's arbitrary int does
# NOT collapse: an int-kept ID silently diverges. R's numeric IS a double, so R
# is accidentally faithful. Naive Python (int) and naive R (double) disagree:
# rung 1 catches, with the twist that only Python needs the fix.
def np_gen(rng):
    cliff = 9007199254740992  # 2**53
    ids = [cliff - 3, cliff - 1, cliff, cliff + 1, cliff + 3, cliff + 5, cliff + 7]
    ids += [rng.randint(1, 10 ** 6) for _ in range(3)]
    rng.shuffle(ids)
    return {"ids": ids[:rng.randint(10, 13)]}


def np_exp(s):
    return {"id": [sas_num(i) for i in s["ids"]],
            "id2": [sas_num(sas_num(i) + 1) for i in s["ids"]]}


def np_py(s, naive):
    core = ("ID=list(X)\nID2=[i+1 for i in X]" if naive else
            "ID=[float(i) for i in X]\nID2=[float(i)+1.0 for i in X]")
    return (f"import pandas as pd\nX={s['ids']!r}\n{core}\n"
            "pd.DataFrame({'id':ID,'id2':ID2}).to_feather('results.feather')\n")


def np_r(s, naive):
    ids = "c(" + ",".join(str(i) for i in s["ids"]) + ")"
    return (f"suppressMessages(library(arrow))\nX<-{ids}\n"
            "write_feather(data.frame(id=X,id2=X+1),'results.feather')\n")


def np_sas(s):
    lines = "\n".join(str(i) for i in s["ids"])
    return f"data w;\n input id;\n id2=id+1;\n datalines;\n{lines}\n;\nrun;\nproc print;run;\n"


FAMILIES = [
    {"name": "round", "salt": 1, "gen": round_gen, "expected": round_exp,
     "py": round_py, "r": round_r, "sas": round_sas},
    {"name": "missing_compare", "salt": 2, "gen": mc_gen, "expected": mc_exp,
     "py": mc_py, "r": mc_r, "sas": mc_sas},
    {"name": "max_ignore_missing", "salt": 3, "gen": mx_gen, "expected": mx_exp,
     "py": mx_py, "r": mx_r, "sas": mx_sas},
    {"name": "intck_year", "salt": 4, "gen": ic_gen, "expected": ic_exp,
     "py": ic_py, "r": ic_r, "sas": ic_sas},
    {"name": "sort_missing_first", "salt": 5, "gen": st_gen, "expected": st_exp,
     "py": st_py, "r": st_r, "sas": st_sas},
    {"name": "numeric_precision", "salt": 6, "gen": np_gen, "expected": np_exp,
     "py": np_py, "r": np_r, "sas": np_sas},
]


def run_family(fam, K, outdir):
    t = {"ran": 0, "fpass": 0, "ncaught": 0, "blind": 0, "ffail": []}
    for k in range(K):
        rng = random.Random(198307 + fam["salt"] * 10007 + k)
        spec = fam["gen"](rng)
        exp = fam["expected"](spec)
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            fp, ep = run_prog("py", fam["py"](spec, False), wd)
            fr, er = run_prog("r", fam["r"](spec, False), wd)
            np_, _ = run_prog("py", fam["py"](spec, True), wd)
            nr, _ = run_prog("r", fam["r"](spec, True), wd)
        if any(v is None for v in (fp, fr, np_, nr)):
            print(f"  {fam['name']:18} seed {k:2d}: RUN FAIL py={ep or '-'} r={er or '-'}")
            continue
        t["ran"] += 1
        r1 = frames_equal(fp, fr)
        r2 = frames_equal(fp, exp) and frames_equal(fr, exp)
        nag = frames_equal(np_, nr)
        ntr = frames_equal(np_, exp)
        blind = nag and not ntr
        ncaught = not (nag and ntr)
        t["fpass"] += (r1 and r2)
        t["ncaught"] += ncaught
        t["blind"] += blind
        if not (r1 and r2):
            t["ffail"].append(k)
        open(f"{outdir}/{fam['name']}_{k:03d}.sas", "w").write(fam["sas"](spec))
        who = "rung1" if not nag else ("rung2 BLIND SPOT" if not ntr else "naive-clean")
        print(f"  {fam['name']:18} seed {k:2d}: faithful[r1 {'ok' if r1 else 'XX'} r2 {'ok' if r2 else 'XX'}]"
              f"  naive caught by {who}")
    return t


def main():
    K = int(os.environ.get("K", "10"))
    os.makedirs(SYNTH_OUT, exist_ok=True)
    print(f"synthesizing {len(FAMILIES)} families x {K} seeds, three-rung gate:\n")
    grand = {"ran": 0, "fpass": 0, "ncaught": 0, "blind": 0, "ffail": 0}
    for fam in FAMILIES:
        t = run_family(fam, K, SYNTH_OUT)
        for key in ("ran", "fpass", "ncaught", "blind"):
            grand[key] += t[key]
        grand["ffail"] += len(t["ffail"])
        flag = f"  <-- FAITHFUL DIVERGED on seeds {t['ffail']}" if t["ffail"] else ""
        print(f"  = {fam['name']:18}: faithful {t['fpass']}/{t['ran']} match truth+agree | "
              f"naive caught {t['ncaught']}/{t['ran']} ({t['blind']} by reference alone){flag}\n")
    print(f"TOTAL: faithful {grand['fpass']}/{grand['ran']} clean | "
          f"naive caught {grand['ncaught']}/{grand['ran']} | "
          f"reference-only catches (rung-1 blind) {grand['blind']} | "
          f"faithful divergences to chase: {grand['ffail']}")
    print(f"SAS staged for live capture -> {SYNTH_OUT}/*.sas")


if __name__ == "__main__":
    main()
