here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data subsetted","set raw","normalized=upcase(compbl(strip(label)))","score=sum(abs(a),abs(b))","if not missing(score) and score>=limit","after=abs(a-b)","put score","run")

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
 normalized<-C('upcase',C('compbl',C('strip',row$label)));score<-C('sum',C('abs',row$a),C('abs',row$b))
 if(!(!cx_truth(C('missing',score)) & cx_truth(cx_cmp(score,row$limit,'ge')))) next
 after<-C('abs',cx_plus(row$a,row$b,TRUE));emit('subsetted',c(row,list(store(normalized,16L),score,after)));logs<-c(logs,L(score))
}
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
