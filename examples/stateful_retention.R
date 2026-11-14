here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'stateful_wave_oracles.R'))
required<-c("data retained_rows","length canon $24","length trace $8","retain peak 0","retain seen 10","retain pending .","set raw","canon=upcase(compbl(dequote(strip(code))))","if n(amount,expected)=2 then do","scratch=abs(amount-expected)","peak=max(peak,scratch)","seen=seen+1","pending=peak","end","trace=ifc(n(amount,expected)=2,'READ','MISS')","output","if n(amount,expected)<2 then do","scratch=99","output","end","put 'retained'","run")
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(sx_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 text<-paste(readLines(args[2],warn=FALSE),collapse='\n')
 parts<-trimws(gsub('[[:space:]]+',' ',strsplit(text,';',fixed=TRUE)[[1]]));parts<-parts[nzchar(parts)]
 if(!identical(parts,required)) stop('original source sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 expected_names<-c("rid","code","amount","expected","enable","batch","limit")
 if(!identical(names(input),expected_names)) stop('input column order')
 rows<-lapply(seq_len(nrow(input)),function(i) {
   row<-lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)
   row[[2]]<-store(input[[2]][i],24L)
   names(row)<-expected_names;row
 })
 cat('STATEMENTS|',length(required),'\n',sep='')
 cat('COLUMNS|raw|rid,code,amount,expected,enable,batch,limit\n')
 cat('COLUMNS|retained_rows|canon,trace,peak,seen,pending,rid,code,amount,expected,enable,batch,limit,scratch\n')
 for(row in rows) emit("raw",row)
 peak<-0;seen<-10;pending<-NA_real_;logs<-character()
 for(row in rows) {
  canon<-C('upcase',C('compbl',C('dequote',C('strip',row$code))));scratch<-NA_real_
  good<-cx_truth(cx_cmp(C('n',row$amount,row$expected),2,'eq'))
  if(good) {scratch<-C('abs',cx_plus(row$amount,row$expected,TRUE));peak<-sx_state(C('max',peak,scratch));seen<-sx_state(cx_plus(seen,1));pending<-peak}
  trace<-C('ifc',as.numeric(good),'READ','MISS')
  snapshot<-function() emit('retained_rows',c(list(store(canon,24L),store(trace,8L),peak,seen,pending),row,list(scratch)))
  snapshot();if(!good) {scratch<-99;snapshot()};logs<-c(logs,'retained')
 }
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
