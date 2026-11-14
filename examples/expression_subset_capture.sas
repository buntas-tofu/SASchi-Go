data subsetted;
set raw;
normalized=upcase(compbl(strip(label)));
score=sum(abs(a),abs(b));
if not missing(score) and score>=limit;
after=abs(a-b);
put score;
run;
