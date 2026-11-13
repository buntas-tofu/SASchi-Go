# Independent first-party R kernels from qualified preimplementation family oracles.
# Independent byte-position oracle. No Python implementation is imported.
txt_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
txt_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
txt_ascii<-function(x) {
 if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
 b<-as.integer(charToRaw(x));if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds');b
}
txt_text<-function(b) rawToChar(as.raw(b))
txt_call_value<-function(name,args) {
 limits<-switch(name,propcase=c(2L,2L),quote=c(1L,2L),dequote=c(1L,1L),countc=c(2L,3L),transtrn=c(3L,3L),stop('name'))
 if(length(args)<limits[1] || length(args)>limits[2]) stop('arity')
 all<-lapply(args,txt_ascii);b<-all[[1]];n<-length(b)
 if(name=='propcase') {
  delimiters<-all[[2]];if(!length(delimiters) || length(delimiters)>64L) stop('delimiters')
  starts<-if(n) c(TRUE,head(b,-1L) %in% delimiters) else logical()
  upper<-b>=65L & b<=90L;b[upper]<-b[upper]+32L
  chosen<-starts & b>=97L & b<=122L;b[chosen]<-b[chosen]-32L
  return(txt_text(b))
 }
 if(name=='quote') {
  q<-if(length(args)==1L) 34L else all[[2]]
  if(length(q)!=1L || !(q %in% c(34L,39L))) stop('quote character')
  result<-c(q,unlist(lapply(b,function(x) if(x==q) c(x,x) else x)),q)
  if(length(result)>200L) stop('QUOTE buffer');return(txt_text(result))
 }
 if(name=='dequote') {
  if(!n || !(b[1L] %in% c(34L,39L))) return(txt_text(b))
  q<-b[1L];out<-integer();i<-2L
  while(i<=n) {
   if(b[i]==q) {if(i<n && b[i+1L]==q) {out<-c(out,q);i<-i+2L;next};break}
   out<-c(out,b[i]);i<-i+1L
  }
  return(txt_text(out))
 }
 if(name=='countc') {
  chars<-all[[2]];if(length(chars)>64L) stop('set bound')
  m<-if(length(args)==3L) toupper(txt_text(all[[3]])) else ''
  if(nchar(m)>3L || grepl('[^IVT]',m)) stop('modifier')
  if(grepl('T',m,fixed=TRUE)) {b<-as.integer(charToRaw(sub(' +$','',txt_text(b))));chars<-as.integer(charToRaw(sub(' +$','',txt_text(chars))))}
  if(grepl('I',m,fixed=TRUE)) {b[b>=65L & b<=90L]<-b[b>=65L & b<=90L]+32L;chars[chars>=65L & chars<=90L]<-chars[chars>=65L & chars<=90L]+32L}
  if(!length(chars)) return(0L)
  found<-b %in% chars;return(sum(if(grepl('V',m,fixed=TRUE)) !found else found))
 }
 target<-all[[2]];replacement<-all[[3]]
 if(!length(target) || length(target)>64L || length(replacement)>64L) stop('replacement bounds')
 out<-integer();i<-1L
 while(i<=n) {
  end<-i+length(target)-1L
  if(end<=n && identical(b[seq.int(i,end)],target)) {out<-c(out,replacement);i<-end+1L} else {out<-c(out,b[i]);i<-i+1L}
 }
 if(length(out)>200L) stop('TRANSTRN result bound');txt_text(out)
}
# Independent byte-array oracle and fixed original-program witness.
pos_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
pos_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
pos_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
pos_call_value<-function(name,args) {
 names<-c('anylower','anyupper','anypunct','anyxdigit','notalpha','notalnum','notspace')
 if(!(name %in% names) || length(args)<1L || length(args)>2L) stop('arity or name')
 b<-pos_ascii(args[[1]]);start<-if(length(args)==2L) args[[2]] else 1
 if(!identical(class(start),'numeric') || length(start)!=1L || is.nan(start)) stop('start type')
 if(is.na(start)) {if(name=='anypunct') stop('conflicting documented missing start');start<-1}
 if(!is.finite(start) || abs(start)>2147483647 || start!=floor(start)) stop('start domain')
 if(start==0 || start>length(b) || !length(b)) return(0L)
 order<-if(start>0) seq.int(start,length(b)) else seq.int(min(-start,length(b)),1L)
 lower<-b>=97L & b<=122L;upper<-b>=65L & b<=90L;digit<-b>=48L & b<=57L
 punctuation<-(b>=33L & b<=47L)|(b>=58L & b<=64L)|(b>=91L & b<=96L)|(b>=123L & b<=126L)
 selected<-switch(name,anylower=lower,anyupper=upper,anypunct=punctuation,anyxdigit=digit|(b>=65L & b<=70L)|(b>=97L & b<=102L),notalpha=!(lower|upper),notalnum=!(lower|upper|digit),notspace=b!=32L)
 positions<-order[selected[order]];if(length(positions)) positions[1L] else 0L
}
# Independent byte-array oracle and fixed original-program witness.
sel_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
sel_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
sel_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
sel_num<-function(x) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(!is.na(x) && (!is.finite(x) || abs(x)>1000000)) stop('numeric bound');x
}
sel_call_value<-function(name,args) {
 if(name %in% c('ifn','ifc')) {
  if(length(args)<3L || length(args)>4L) stop('IF arity')
  flag<-sel_num(args[[1]]);choices<-args[-1L]
  if(name=='ifn') choices<-lapply(choices,sel_num) else {
   bytes<-lapply(choices,sel_ascii);if(any(lengths(bytes)>200L)) stop('character choice bound')
  }
  selected<-if(is.na(flag)) {if(length(choices)==3L) 3L else 2L} else if(flag!=0) 1L else 2L
  return(choices[[selected]])
 }
 if(!(name %in% c('choosen','choosec','whichn','whichc')) || length(args)<2L || length(args)>32L) stop('name or arity')
 character<-name %in% c('choosec','whichc')
 if(startsWith(name,'choose')) {
  index<-sel_num(args[[1]]);choices<-args[-1L]
  if(character) {bytes<-lapply(choices,sel_ascii);if(any(lengths(bytes)>200L)) stop('character bound')} else choices<-lapply(choices,sel_num)
  if(is.na(index) || index!=floor(index) || index==0 || abs(index)>length(choices)) stop('CHOOSE index domain')
  selected<-if(index>0) index else length(choices)+index+1L;return(choices[[selected]])
 }
 if(character) {
  all<-lapply(args,sel_ascii);if(any(lengths(all)>200L)) stop('character bound')
  values<-vapply(args,function(x) sub(' +$','',x),'');if(!nzchar(values[1L])) return(NA_real_)
 } else {values<-unlist(lapply(args,sel_num));if(is.na(values[1L])) return(NA_real_)}
 found<-which(!is.na(values[-1L]) & values[-1L]==values[1L]);if(length(found)) found[1L] else 0L
}
# Independent byte-array oracle and fixed original-program witness.
rank_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
rank_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
rank_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
rank_integer_value<-function(x,low=-1000000,high=1000000,missing=TRUE) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(is.na(x)) {if(missing) return(x);stop('missing')}
 if(!is.finite(x) || x<low || x>high || x!=floor(x)) stop('integer domain');x
}
rank_call_value<-function(name,args) {
 ranked<-name %in% c('largest','smallest')
 if(!(name %in% c('largest','smallest','css','uss')) || length(args)<if(ranked) 2L else 1L || length(args)>if(ranked) 33L else 32L) stop('arity or name')
 values<-unlist(lapply(if(ranked) args[-1L] else args,rank_integer_value));nargs<-length(values)
 if(ranked) k<-rank_integer_value(args[[1]],1,nargs,FALSE)
 values<-values[!is.na(values)];n<-length(values)
 if(ranked) {if(k>n) return(NA_real_);return(sort(values,decreasing=name=='largest')[k])}
 if(!n) return(NA_real_)
 if(name=='uss') return(sum(values*values))
 # Pairwise identity avoids subtracting large nearly equal raw sums.
 if(n==1L) return(0)
 pairs<-combn(values,2L);sum((pairs[1L,]-pairs[2L,])^2)/n
}
# Independent byte-array oracle and fixed original-program witness.
zero_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
zero_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
zero_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
zero_bounded<-function(x) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(!is.na(x) && (!is.finite(x) || abs(x)>1000000 || (x!=0 && abs(x)<2^-40))) stop('zero_bounded normal operand');x
}
zero_unit_value<-function(x,signed=FALSE) {
 x<-zero_bounded(x);if(is.na(x)) return(x)
 if(x==0 || (!signed && x<0)) stop('nonzero unit')
 if(!(abs(x) %in% (2^seq.int(-10L,10L)))) stop('power of two unit');x
}
zero_call_value<-function(name,args) {
 if(!(name %in% c('ceilz','floorz','intz','roundz','modz'))) stop('name')
 lower<-if(name=='modz') 2L else 1L;upper<-if(name %in% c('roundz','modz')) 2L else 1L
 if(length(args)<lower || length(args)>upper) stop('arity')
 x<-zero_bounded(args[[1]])
 unit<-if(name %in% c('roundz','modz')) zero_unit_value(if(length(args)==2L) args[[2]] else 1,name=='modz') else 1
 if(is.na(x) || is.na(unit)) return(NA_real_)
 answer<-switch(name,ceilz=ceiling(x),floorz=floor(x),intz=trunc(x),roundz=round(x/unit)*unit,modz=sign(x)*(abs(x)%%abs(unit)))
 if(answer==0) 0 else answer
}
# Independent byte-array oracle and fixed original-program witness.
cal_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
cal_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
cal_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
cal_integer_value<-function(x,low,high) {
 if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
 if(is.na(x)) return(x)
 if(!is.finite(x) || x<low || x>high || x!=floor(x)) stop('integer domain');x
}
cal_epoch<-as.Date('1960-01-01');cal_min_day<-as.numeric(as.Date('1753-01-01')-cal_epoch);cal_max_day<-as.numeric(as.Date('3999-12-31')-cal_epoch)
cal_call_value<-function(name,args) {
 limits<-switch(name,hms=list(c(0,23),c(0,59),c(0,59)),yyq=list(c(1753,3999),c(1,4)),datejul=list(c(1753001,3999366)),juldate7=list(c(cal_min_day,cal_max_day)),stop('name'))
 if(length(args)!=length(limits)) stop('arity')
 values<-mapply(function(x,bounds) cal_integer_value(x,bounds[1],bounds[2]),args,limits)
 if(any(is.na(values))) return(NA_real_)
 if(name=='hms') return(sum(values*c(3600,60,1)))
 if(name=='yyq') return(as.numeric(as.Date(sprintf('%04d-%02d-01',values[1],3L*values[2]-2L))-cal_epoch))
 if(name=='datejul') {
  year<-values[1]%/%1000;day<-values[1]%%1000
  start<-as.Date(sprintf('%04d-01-01',year));last<-as.Date(sprintf('%04d-12-31',year))
  if(day<1 || day>as.numeric(last-start)+1L) stop('ordinal day domain')
  return(as.numeric(start+day-1L-cal_epoch))
 }
 date<-cal_epoch+values[1];as.numeric(format(date,'%Y'))*1000+as.numeric(format(date,'%j'))
}
unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')

oracle_call<-function(name,args) {
 key<-strsplit(name,':',fixed=TRUE)[[1]];if(length(key)!=2L) stop('kernel identity')
 modules<-list(txt=txt_call_value,pos=pos_call_value,sel=sel_call_value,rank=rank_call_value,zero=zero_call_value,cal=cal_call_value)
 if(!(key[1] %in% names(modules))) stop('kernel module');modules[[key[1]]](key[2],args)
}
