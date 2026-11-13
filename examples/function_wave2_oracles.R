# Independent first-party R kernels, copied from frozen qualified family oracles.
# Identifier prefixes isolate modules; no Python implementation is imported.
# Independent byte-array oracle and fixed original-program witness.
ws_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
ws_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ws_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
ws_call_value<-function(name,args) {
  if(length(args)!=1L) stop('arity')
  b<-ws_ascii(args[[1]]);n<-length(b)
  if(name=='left') {
    first<-which(b!=32L)
    if(!length(first)) return(rawToChar(as.raw(b)))
    i<-first[1];return(rawToChar(as.raw(c(b[seq.int(i,n)],rep(32L,i-1L)))))
  }
  if(name=='right') {
    last<-which(b!=32L)
    if(!length(last)) return(rawToChar(as.raw(b)))
    i<-tail(last,1L);return(rawToChar(as.raw(c(rep(32L,n-i),b[seq_len(i)]))))
  }
  if(name=='compbl') {
    selected<-if(n) c(TRUE,!(head(b,-1L)==32L & tail(b,-1L)==32L)) else logical()
    return(rawToChar(as.raw(b[selected])))
  }
  if(name!='trimn') stop('name')
  last<-which(b!=32L)
  rawToChar(as.raw(if(length(last)) b[seq_len(tail(last,1L))] else integer()))
}
# Independent byte-array oracle and fixed original-program witness.
cat_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
cat_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
cat_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
cat_call_value<-function(name,args) {
  if(!(name %in% c('cat','cats','catt')) || length(args)<1L || length(args)>32L) stop('arity or name')
  pieces<-lapply(args,cat_ascii)
  if(name!='cat') pieces<-lapply(pieces,function(b) {
    nonblank<-which(b!=32L)
    if(!length(nonblank)) return(integer())
    if(name=='cats') b[seq.int(nonblank[1],tail(nonblank,1L))] else b[seq_len(tail(nonblank,1L))]
  })
  if(sum(lengths(pieces))>200L) stop('result bound')
  rawToChar(as.raw(unlist(pieces)))
}
# Independent byte-array oracle and fixed original-program witness.
val_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
val_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
val_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
val_call_value<-function(name,args) {
  names<-c('anyalpha','anydigit','anyalnum','anyspace','notdigit')
  if(name=='verify') {
    if(length(args)<2L || length(args)>32L) stop('VERIFY arity')
    all<-lapply(args,val_ascii);allowed<-unlist(all[-1L]);positions<-which(!(all[[1]] %in% allowed))
    return(if(length(positions)) positions[1L] else 0L)
  }
  if(!(name %in% names) || length(args)<1L || length(args)>2L) stop('ANY arity')
  b<-val_ascii(args[[1]]);start<-if(length(args)==2L) args[[2]] else 1
  if(!identical(class(start),'numeric') || length(start)!=1L) stop('start type')
  if(is.na(start)) start<-1
  if(!is.finite(start) || abs(start)>2147483647 || start!=floor(start)) stop('start domain')
  if(start==0 || start>length(b) || !length(b)) return(0L)
  order<-if(start>0) seq.int(start,length(b)) else seq.int(min(-start,length(b)),1L)
  alpha<-(b>=65L & b<=90L) | (b>=97L & b<=122L);digit<-b>=48L & b<=57L
  selected<-switch(name,anyalpha=alpha,anydigit=digit,anyalnum=alpha|digit,anyspace=b==32L,notdigit=!digit)
  positions<-order[selected[order]]
  if(length(positions)) positions[1L] else 0L
}
# Independent byte-array oracle and fixed original-program witness.
search_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
search_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
search_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
search_integer_value<-function(x,missing=FALSE) {
  if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
  if(is.na(x)) {if(missing) return(NA_real_);stop('missing numeric')}
  if(!is.finite(x) || abs(x)>2147483647 || x!=floor(x)) stop('numeric domain')
  x
}
search_positions<-function(n,start) {
  start<-search_integer_value(start)
  if(!n || start==0 || start>n) return(integer())
  if(start>0) seq.int(start,n) else seq.int(min(-start,n),1L)
}
search_fold<-function(b) {chosen<-b>=65L & b<=90L;b[chosen]<-b[chosen]+32L;b}
search_options<-function(args,allowed) {
  modifier<-NULL;start<-NULL
  for(x in args) {
    if(identical(class(x),'character')) {
      search_ascii(x)
      if(!is.null(modifier) || !(toupper(x) %in% allowed)) stop('modifier')
      modifier<-toupper(x)
    } else {
      if(!is.null(start)) stop('duplicate start')
      start<-search_integer_value(x)
    }
  }
  list(modifier=if(is.null(modifier)) '' else modifier,start=if(is.null(start)) 1 else start)
}
search_word_match<-function(source,word,delimiters,order) {
  n<-length(source);m<-length(word)
  for(i in order) {
    end<-i+m-1L
    if(end>n || !m) next
    if(!identical(source[seq.int(i,end)],word)) next
    if((i==1L || source[i-1L] %in% delimiters) && (end==n || source[end+1L] %in% delimiters)) return(i)
  }
  0L
}
search_call_value<-function(name,args) {
  if(name=='indexc') {
    if(length(args)<2L || length(args)>32L) stop('arity')
    bytes<-lapply(args,search_ascii);found<-which(bytes[[1]] %in% unlist(bytes[-1L]))
    return(if(length(found)) found[1L] else 0L)
  }
  if(name=='substrn') {
    if(length(args)<2L || length(args)>3L) stop('arity')
    b<-search_ascii(args[[1]]);position<-search_integer_value(args[[2]],TRUE)
    count<-if(length(args)==3L) search_integer_value(args[[3]],TRUE) else length(b)-position+1
    if(is.na(position) || is.na(count) || count<=0) return('')
    last<-min(length(b),position+count-1);first<-max(1,position)
    if(first>last) return('')
    return(rawToChar(as.raw(b[seq.int(first,last)])))
  }
  if(name=='findc') {
    if(length(args)<2L || length(args)>4L) stop('arity')
    b<-search_ascii(args[[1]]);chars<-search_ascii(args[[2]]);if(length(chars)>64L) stop('set bound')
    control<-search_options(args[-seq_len(2L)],c('','I','K','IK','KI'))
    if(grepl('I',control$modifier,fixed=TRUE)) {b<-search_fold(b);chars<-search_fold(chars)}
    selected<-b %in% chars;if(grepl('K',control$modifier,fixed=TRUE)) selected<-!selected
    order<-search_positions(length(b),control$start);found<-order[selected[order]]
    return(if(length(found)) found[1L] else 0L)
  }
  if(name=='indexw') {
    if(length(args)<2L || length(args)>3L) stop('arity')
    b<-search_ascii(args[[1]]);word<-search_ascii(args[[2]])
    if(length(args)==3L && !identical(rawToChar(as.raw(search_ascii(args[[3]]))),' ')) stop('INDEXW delimiter')
    nonblank<-which(word!=32L)
    word<-if(length(nonblank)) word[seq.int(nonblank[1],tail(nonblank,1L))] else integer()
    if(!length(word)) return(if(all(b==32L)) 1L else 0L)
    return(search_word_match(b,word,32L,seq_len(length(b))))
  }
  if(name!='findw' || length(args)<3L || length(args)>5L) stop('arity')
  b<-search_ascii(args[[1]]);word<-search_ascii(args[[2]]);chars<-search_ascii(args[[3]])
  if(!length(word) || !length(chars) || length(chars)>64L || any((chars>=65L & chars<=90L) | (chars>=97L & chars<=122L))) stop('word or delimiter domain')
  control<-search_options(args[-seq_len(3L)],c('','I'))
  if(control$modifier=='I') {b<-search_fold(b);word<-search_fold(word)}
  search_word_match(b,word,chars,search_positions(length(b),control$start))
}
# Independent byte-array oracle and fixed original-program witness.
stats_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
stats_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
stats_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
stats_call_value<-function(name,args) {
  if(!(name %in% c('median','range','var','std')) || length(args)<1L || length(args)>32L) stop('arity')
  values<-vapply(args,function(x) {
    if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('type')
    if(!is.na(x) && (!is.finite(x) || abs(x)>1000000 || x!=floor(x))) stop('domain')
    x
  },0)
  values<-values[!is.na(values)];n<-length(values)
  if(!n) return(NA_real_)
  if(name=='median') {
    v<-sort(values);return(if(n%%2L) v[(n+1L)/2L] else (v[n/2L]+v[n/2L+1L])/2)
  }
  if(name=='range') return(max(values)-min(values))
  if(n<2L) return(NA_real_)
  differences<-outer(values,values,'-')
  variance<-sum(differences*differences)/(2*n*(n-1))
  if(name=='std') sqrt(variance) else variance
}
# Independent byte-array oracle and fixed original-program witness.
dt_unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
dt_hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
dt_ascii<-function(x) {
  if(!identical(class(x),'character') || length(x)!=1L || is.na(x)) stop('character')
  b<-as.integer(charToRaw(x))
  if(length(b)>32767L || any(b<32L | b>126L)) stop('ASCII bounds')
  b
}
dt_MIN_DAY<--75604
dt_MAX_DAY<-745094
dt_MIN_STAMP<--6532185600
dt_MAX_STAMP<-64376207999
dt_integer_value<-function(x,low,high) {
  if(!identical(class(x),'numeric') || length(x)!=1L || is.nan(x)) stop('numeric type')
  if(is.na(x)) return(NA_real_)
  if(!is.finite(x) || x<low || x>high || x!=floor(x)) stop('numeric domain')
  x
}
dt_origin<-as.POSIXct('1960-01-01 00:00:00',tz='UTC')
dt_call_value<-function(name,args) {
  if(name=='dhms') {
    if(length(args)!=4L) stop('arity')
    values<-c(dt_integer_value(args[[1]],dt_MIN_DAY,dt_MAX_DAY),dt_integer_value(args[[2]],0,23),dt_integer_value(args[[3]],0,59),dt_integer_value(args[[4]],0,59))
    if(anyNA(values)) return(NA_real_)
    civil<-paste(format(as.Date(values[1],origin='1960-01-01'),'%Y-%m-%d'),sprintf('%02d:%02d:%02d',as.integer(values[2]),as.integer(values[3]),as.integer(values[4])))
    return(as.numeric(as.POSIXct(civil,format='%Y-%m-%d %H:%M:%S',tz='UTC'))-as.numeric(dt_origin))
  }
  if(length(args)!=1L) stop('arity')
  if(name=='qtr') {
    value<-dt_integer_value(args[[1]],dt_MIN_DAY,dt_MAX_DAY)
    if(is.na(value)) return(NA_real_)
    month<-as.integer(format(as.Date(value,origin='1960-01-01'),'%m'))
    return(ceiling(month/3))
  }
  if(!(name %in% c('datepart','timepart','hour','minute','second'))) stop('name')
  value<-dt_integer_value(args[[1]],dt_MIN_STAMP,dt_MAX_STAMP)
  if(is.na(value)) return(NA_real_)
  civil<-as.POSIXct(value,origin='1960-01-01',tz='UTC')
  if(name=='datepart') return(as.numeric(as.Date(civil,tz='UTC')-as.Date('1960-01-01')))
  parts<-as.numeric(format(civil,c('%H','%M','%S'),tz='UTC'))
  if(name=='timepart') return(sum(parts*c(3600,60,1)))
  parts[match(name,c('hour','minute','second'))]
}
dt_date9<-function(value) {
  if(is.na(value)) return(paste0(strrep(' ',8),'.'))
  civil<-as.Date(value,origin='1960-01-01');month<-as.integer(format(civil,'%m'))
  paste0(format(civil,'%d'),c('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')[month],format(civil,'%Y'))
}

unhex<-function(x) {if(!nzchar(x)) return('');rawToChar(as.raw(strtoi(substring(x,seq(1,nchar(x),2),seq(2,nchar(x),2)),16L)))}
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
decode<-function(x) {kind<-substr(x,1,1);v<-substring(x,3);switch(kind,c=unhex(v),n=as.numeric(v),m=NA_real_,t=structure(v,class='tagged'),b=TRUE,stop('encoding'))}
encode<-function(x) if(is.character(x)) paste0('c:',hex(x)) else if(is.na(x)) 'm:' else paste0('n:',sprintf('%.17g',x))
store<-function(x,w) paste0(substr(x,1,w),strrep(' ',max(0,w-nchar(x,type='bytes'))))
emit<-function(name,row) cat(paste(c('ROW',name,vapply(row,encode,'')),collapse='|'),'\n',sep='')
upper_text<-function(x) {b<-ws_ascii(x);selected<-b>=97L & b<=122L;b[selected]<-b[selected]-32L;rawToChar(as.raw(b))}
lower_text<-function(x) {b<-ws_ascii(x);selected<-b>=65L & b<=90L;b[selected]<-b[selected]+32L;rawToChar(as.raw(b))}
strip_text<-function(x) {b<-ws_ascii(x);positions<-which(b!=32L);rawToChar(as.raw(if(length(positions)) b[seq.int(positions[1],tail(positions,1L))] else integer()))}
word_parts<-function(x) {x<-strip_text(x);if(!nzchar(x)) character() else Filter(nzchar,strsplit(x,' ',fixed=TRUE)[[1]])}
compress_blanks<-function(x) {b<-ws_ascii(x);rawToChar(as.raw(b[b!=32L]))}
missing_value<-function(x) if(is.character(x)) as.numeric(all(ws_ascii(x)==32L)) else as.numeric(is.na(x))
old_mean<-function(values) {values<-unlist(values);values<-values[!is.na(values)];if(length(values)) sum(values)/length(values) else NA_real_}
month_begin<-function(day) {if(is.na(day)) return(NA_real_);d<-as.Date(day,origin='1960-01-01');as.numeric(as.Date(format(d,'%Y-%m-01'))-as.Date('1960-01-01'))}
month_distance<-function(day) {if(is.na(day)) return(NA_real_);d<-as.Date(day,origin='1960-01-01');12*(as.integer(format(d,'%Y'))-1960)+as.integer(format(d,'%m'))-1}
calendar_part<-function(day,part) {if(is.na(day)) return(NA_real_);as.numeric(format(as.Date(day,origin='1960-01-01'),part))}
oracle_call<-function(name,args) {
  key<-strsplit(name,':',fixed=TRUE)[[1]]
  if(length(key)!=2L) stop('kernel identity')
  modules<-list(ws=ws_call_value,cat=cat_call_value,val=val_call_value,search=search_call_value,stats=stats_call_value,dt=dt_call_value)
  if(!(key[1] %in% names(modules))) stop('kernel module')
  modules[[key[1]]](key[2],args)
}
