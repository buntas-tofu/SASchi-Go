here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'stateful_wave_oracles.R'))
required<-c("data quality_audit","length record_key $24","length reason $12","set submissions","record_key=upcase(compbl(dequote(strip(raw_id))))","bad_id=notalnum(strip(record_key))>0 or lengthn(strip(record_key))=0","bad_measure=n(value,lower,upper)<3 or lower>upper or value<lower or value>upper","if bad_id then do","reason='IDENTIFIER'","output","end","if bad_measure then do","reason='MEASUREMENT'","output","end","if not bad_id and not bad_measure then do","reason='ACCEPT'","output","end","run","data review_queue","set quality_audit","where reason^='ACCEPT'","run")
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(sx_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 text<-paste(readLines(args[2],warn=FALSE),collapse='\n')
 parts<-trimws(gsub('[[:space:]]+',' ',strsplit(text,';',fixed=TRUE)[[1]]));parts<-parts[nzchar(parts)]
 if(!identical(parts,required)) stop('original source sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 expected_names<-c("row_id","raw_id","value","lower","upper")
 if(!identical(names(input),expected_names)) stop('input column order')
 rows<-lapply(seq_len(nrow(input)),function(i) {
   row<-lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)
   row[[2]]<-store(input[[2]][i],24L)
   names(row)<-expected_names;row
 })
 cat('STATEMENTS|',length(required),'\n',sep='')
 cat('COLUMNS|submissions|row_id,raw_id,value,lower,upper\n')
 cat('COLUMNS|quality_audit|record_key,reason,row_id,raw_id,value,lower,upper,bad_id,bad_measure\n')
 cat('COLUMNS|review_queue|record_key,reason,row_id,raw_id,value,lower,upper,bad_id,bad_measure\n')
 for(row in rows) emit("submissions",row)
 audit_rows<-list()
 for(row in rows) {
  key<-C('upcase',C('compbl',C('dequote',C('strip',row$raw_id))))
  bad_id<-as.numeric(C('notalnum',C('strip',store(key,24L)))>0 || C('lengthn',C('strip',store(key,24L)))==0)
  bad_measure<-as.numeric(C('n',row$value,row$lower,row$upper)<3 || cx_truth(cx_cmp(row$lower,row$upper,'gt')) || cx_truth(cx_cmp(row$value,row$lower,'lt')) || cx_truth(cx_cmp(row$value,row$upper,'gt')))
  reasons<-c(if(bad_id) 'IDENTIFIER',if(bad_measure) 'MEASUREMENT',if(!bad_id && !bad_measure) 'ACCEPT')
  for(reason in reasons) {out<-c(list(store(key,24L),store(reason,12L)),row,list(bad_id,bad_measure));audit_rows[[length(audit_rows)+1L]]<-out;emit('quality_audit',out)}
 }
 for(out in audit_rows) if(out[[2]]!=store('ACCEPT',12L)) emit('review_queue',out)
} else stop('mode')
