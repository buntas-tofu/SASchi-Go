data selectors;
set raw;
pick=ifn((nmiss(a,b)=0 and abs(a-b)<=limit),largest(k,a,b,c),coalesce(a,b,0));
four=ifn(flag,abs(a),abs(b),0);
status=ifc(notalnum(strip(code))=0,upcase(strip(code)),propcase(strip(label),' -'));
key=cats(ifc(flag,upcase(tag),lowcase(tag)),'-',strip(code));
put key;
put pick;
run;
