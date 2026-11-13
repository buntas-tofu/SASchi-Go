data joined;
set raw;
rawcat=cat(a,b);
tight=cats(a,b);
tails=catt(a,b);
output;
if tight ne '                                                                                                                                                                                                        ' then put tight;
if tails ne '                                                                                                                                                                                                        ' then put tails;
run;
