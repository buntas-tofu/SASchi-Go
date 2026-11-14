here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data selectors","set raw","pick=ifn((nmiss(a,b)=0 and abs(a-b)<=limit),largest(k,a,b,c),coalesce(a,b,0))","four=ifn(flag,abs(a),abs(b),0)","status=ifc(notalnum(strip(code))=0,upcase(strip(code)),propcase(strip(label),' -'))","key=cats(ifc(flag,upcase(tag),lowcase(tag)),'-',strip(code))","put key","put pick","run")

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
 test<-as.numeric(cx_truth(cx_cmp(C('nmiss',a,b),0,'eq')) & cx_truth(cx_cmp(C('abs',cx_plus(a,b,TRUE)),row$limit,'le')))
 pick<-C('ifn',test,C('largest',row$k,a,b,c),C('coalesce',a,b,0));four<-C('ifn',row$flag,C('abs',a),C('abs',b),0)
 status<-C('ifc',cx_cmp(C('notalnum',C('strip',row$code)),0,'eq'),C('upcase',C('strip',row$code)),C('propcase',C('strip',row$label),' -'))
 key<-C('cats',C('ifc',row$flag,C('upcase',row$tag),C('lowcase',row$tag)),'-',C('strip',row$code))
 emit('selectors',c(row,list(pick,four,store(status,200L),store(key,200L))));logs<-c(logs,T(key),L(pick))
}
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
