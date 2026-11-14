here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data comparisons","set raw","hit=(largest(k,a,b,c)>=coalesce(limit,0))","same=(upcase(strip(code))=upcase(strip(tag)))","bad=notalnum(upcase(strip(code)))","size=lengthn(strip(label))","if notalnum(strip(code)) then review=1","else review=0","below=(a<0)","put hit","run")

args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
 cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 for(i in seq_len(nrow(cases))) cat(tryCatch(encode(cx_call(cases$name[i],lapply(strsplit(cases$args[i],'|',fixed=TRUE)[[1]],decode))),error=function(e) 'REFUSE'),'\n',sep='')
} else if(args[1]=='program') {
 text<-paste(readLines(args[2],warn=FALSE),collapse='\n');parts<-trimws(strsplit(text,';',fixed=TRUE)[[1]]);parts<-parts[nzchar(parts)]
 if(!identical(parts,required)) stop('original sequence')
 input<-read.csv(args[3],colClasses='character',na.strings=NULL,check.names=FALSE,blank.lines.skip=FALSE)
 expected_names<-c('rid','label','code','tag','a','b','c','k','flag','limit','low','high')
 if(!identical(names(input),expected_names)) stop('input schema')
 rows<-lapply(seq_len(nrow(input)),function(i) {
   row<-lapply(input[i,],function(x) if(nzchar(x)) as.numeric(x) else NA_real_)
   row[[2]]<-store(input$label[i],16L);row[[3]]<-store(input$code[i],12L);row[[4]]<-store(input$tag[i],4L);names(row)<-expected_names;row
 })
 cat('STATEMENTS|',length(required),'\n',sep='')
 for(row in rows) emit('raw',row)
 logs<-character()
for(row in rows) {
 a<-row$a;b<-row$b;c<-row$c
 hit<-cx_cmp(C('largest',row$k,a,b,c),C('coalesce',row$limit,0),'ge')
 same<-cx_cmp(C('upcase',C('strip',row$code)),C('upcase',C('strip',row$tag)),'eq')
 bad<-C('notalnum',C('upcase',C('strip',row$code)));size<-C('lengthn',C('strip',row$label));review<-B(C('notalnum',C('strip',row$code)));below<-cx_cmp(a,0,'lt')
 emit('comparisons',c(row,list(hit,same,bad,size,review,below)));logs<-c(logs,L(hit))
}
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
