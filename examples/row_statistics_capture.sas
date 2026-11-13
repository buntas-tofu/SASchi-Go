data stats;
set raw;
mid=median(a,b,c);
spread=range(a,b,c);
variance=var(a,b,c);
deviation=std(a,b,c);
output;
put 'measured';
run;
