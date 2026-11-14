here<-dirname(normalizePath(sub('^--file=','',commandArgs()[grep('^--file=',commandArgs())][1])))
source(file.path(here,'composition_wave_oracles.R'))
required<-c("data char_trees","set raw","canon=upcase(compbl(strip(dequote(label))))","key=cats(substrn(upcase(strip(code)),1,4),'-',propcase(strip(label),' -'))","clean=transtrn(upcase(strip(label)),'-',trimn(' '))","edge=catx('|',strip(tag),dequote(strip(code)))","sentinel=catx('|',upcase(trimn(' ')),'Z')","lower=lowcase(cats(strip(tag),strip(code)))","spaced=transtrn('a-b','-',trim(' '))","deleted=transtrn('a-b','-',trimn(' '))","put key","run")

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
 label<-row$label;code<-row$code;tag<-row$tag
 canon<-C('upcase',C('compbl',C('strip',C('dequote',label))))
 key<-C('cats',C('substrn',C('upcase',C('strip',code)),1,4),'-',C('propcase',C('strip',label),' -'))
 clean<-C('transtrn',C('upcase',C('strip',label)),'-',C('trimn',' '))
 edge<-C('catx','|',C('strip',tag),C('dequote',C('strip',code)))
 sentinel<-C('catx','|',C('upcase',C('trimn',' ')),'Z')
 lower<-C('lowcase',C('cats',C('strip',tag),C('strip',code)))
 spaced<-C('transtrn','a-b','-',C('trim',' '));deleted<-C('transtrn','a-b','-',C('trimn',' '))
 emit('char_trees',c(row,list(store(canon,16L),store(key,200L),store(clean,200L),store(edge,200L),store(sentinel,200L),store(lower,200L),store(spaced,200L),store(deleted,200L))));logs<-c(logs,T(key))
}
 for(record in logs) cat('LOG|',hex(record),'\n',sep='')
} else stop('mode')
