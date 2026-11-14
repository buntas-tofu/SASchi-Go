data filtered;
set raw;
where not missing(a) and (flag or lengthn(strip(code))>0);
score=sum(abs(a),abs(b));
label_norm=upcase(strip(label));
put score;
run;
