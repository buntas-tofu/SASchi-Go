here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'stateful_wave_oracles.R'))
required<-c("data decision_rows","length canon $24","length phase $8","length choice $8","set raw","canon=upcase(compbl(dequote(strip(code))))","invalid=notalnum(strip(canon))>0 or lengthn(strip(canon))=0","count=n(amount,expected)","difference=amount-expected","magnitude=abs(difference)","scale=max(abs(amount),abs(expected))","choice=ifc(count=2 and magnitude<=5,'SMALL','REVIEW')","if invalid then do","phase='ID'","output","end","if count=2 and magnitude>2 then do","phase='VALUE'","output decision_rows","difference=0","end","if not invalid and count=2 and magnitude<=2 then do","phase='PASS'","output","end","tail=42","put 'decision'","run")
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
 cat('COLUMNS|decision_rows|canon,phase,choice,rid,code,amount,expected,enable,batch,limit,invalid,count,difference,magnitude,scale,tail\n')
 for(row in rows) emit("raw",row)
 logs<-character()
 for(row in rows) {
  canon<-C('upcase',C('compbl',C('dequote',C('strip',row$code))))
  invalid<-as.numeric(cx_truth(cx_cmp(C('notalnum',C('strip',store(canon,24L))),0,'gt')) | cx_truth(cx_cmp(C('lengthn',C('strip',store(canon,24L))),0,'eq')))
  count<-C('n',row$amount,row$expected);difference<-cx_plus(row$amount,row$expected,TRUE);magnitude<-C('abs',difference);scale<-C('max',C('abs',row$amount),C('abs',row$expected))
  choice<-C('ifc',as.numeric(cx_truth(cx_cmp(count,2,'eq')) & cx_truth(cx_cmp(magnitude,5,'le'))),'SMALL','REVIEW')
  snapshot<-function(phase) emit('decision_rows',c(list(store(canon,24L),store(phase,8L),store(choice,8L)),row,list(invalid,count,difference,magnitude,scale,NA_real_)))
  if(cx_truth(invalid)) snapshot('ID')
  if(cx_truth(cx_cmp(count,2,'eq')) & cx_truth(cx_cmp(magnitude,2,'gt'))) {snapshot('VALUE');difference<-0}
  if(!cx_truth(invalid) & cx_truth(cx_cmp(count,2,'eq')) & cx_truth(cx_cmp(magnitude,2,'le'))) snapshot('PASS')
  logs<-c(logs,'decision')
 }
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
