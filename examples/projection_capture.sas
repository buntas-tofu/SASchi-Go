data source;
length tag $4;
tag='seed';
a=1;
b=2;
c=3;
output;
a=4;
output;
keep c a tag;
run;

data capture(drop=b);
set source(keep=a c tag);
b=a+c;
output;
b=99;
output;
put b= tag=;
run;

data fresh;
set source(drop=c);
before=c;
c=7;
keep c before a tag;
run;
