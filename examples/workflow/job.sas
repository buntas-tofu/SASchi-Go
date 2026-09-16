data rounded; set raw; amount=round(amount,1); run;
proc sort data=rounded out=ordered; by id; run;
proc sort data=lookup out=keys; by id; run;
data joined; merge ordered keys; by id; run;
