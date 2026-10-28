# DS-042 independent base-R records and complete-program witnesses. No live SAS.
decode_literal <- function(token) {
  chars<-strsplit(token,'',fixed=TRUE)[[1]]; n<-length(chars)
  if(n<2L || !(chars[1] %in% c("'",'"')) || chars[n]!=chars[1]) stop('literal')
  q<-chars[1]; body<-if(n==2L) character() else chars[2:(n-1L)]
  if(q=='"' && any(body %in% c('&','%'))) stop('macro')
  out<-character(); at<-1L
  while(at<=length(body)) {
    ch<-body[at]
    if(ch==q) {
      if(at==length(body) || body[at+1L]!=q) stop('literal')
      at<-at+1L
    }
    out<-c(out,ch); at<-at+1L
  }
  result<-if(!length(body)) q else paste0(out,collapse='')
  if(any(utf8ToInt(result)<32L | utf8ToInt(result)>126L)) stop('ASCII')
  result
}
hex<-function(text) paste(sprintf('%02x',as.integer(charToRaw(text))),collapse='')
render<-function(fields) {
  if(nrow(fields)<2L || nrow(fields)>64L) stop('items')
  if(!setequal(fields$kind,c('literal','numeric'))) stop('kinds')
  out<-''
  for(i in seq_len(nrow(fields))) {
    r<-fields[i,]
    if(r$kind=='literal') {
      if(r$type!='text') stop('literal type')
      piece<-decode_literal(r$value)
    } else {
      if(r$type=='missing') piece<-'.' else {
        if(r$type!='number') stop('numeric type')
        x<-suppressWarnings(as.numeric(r$value))
        if(!is.finite(x) || abs(x)>99999999999 || x!=trunc(x)) stop('numeric bound')
        piece<-if(x==0) '0' else sprintf('%.0f',x)
      }
      piece<-paste0(piece,' ')
    }
    out<-paste0(out,piece)
  }
  if(nchar(out,type='bytes')>64L) stop('width')
  out
}
args<-commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases<-read.csv(args[2],colClasses='character',na.strings=NULL,check.names=FALSE,fileEncoding='UTF-8')
  for(id in unique(cases$id)) {
    fields<-cases[cases$id==id & cases$kind!='empty',,drop=FALSE]
    out<-tryCatch(paste0('OK:',hex(render(fields))),error=function(e) 'REFUSE')
    cat(out,'\n',sep='')
  }
} else if(args[1]=='program') {
  source<-paste(readLines(args[2],warn=FALSE),collapse='\n')
  source<-gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  st<-trimws(strsplit(source,';',fixed=TRUE)[[1]]);st<-st[nzchar(st)]
  if(length(st)!=13L) stop('complete statement accounting')
  capture<-function(pattern,text) {
    x<-regmatches(text,regexec(paste0('(?i)^',pattern,'$'),text,perl=TRUE))[[1]]
    if(!length(x)) stop('unhandled statement')
    x[-1]
  }
  # Parse every original statement and bind its identifiers, without a SAS plan.
  capture('data\\s+_null_',st[1]);capture('run',st[13])
  init1<-capture('([a-z_][a-z0-9_]*)\\s*=\\s*([0-9]+)',st[2])
  init2<-capture('([a-z_][a-z0-9_]*)\\s*=\\s*([0-9]+)',st[3])
  decl<-capture('array\\s+([a-z_][a-z0-9_]*)\\{([0-9]+)\\}',st[4])
  outer<-capture('do\\s+([a-z_][a-z0-9_]*)\\s*=\\s*([0-9]+)\\s+to\\s+([0-9]+)',st[5])
  inner<-capture('do\\s+([a-z_][a-z0-9_]*)\\s*=\\s*([a-z_][a-z0-9_]*)\\s+to\\s+([0-9]+)\\s+by\\s+([a-z_][a-z0-9_]*)',st[6])
  yes<-capture('if\\s+([a-z_][a-z0-9_]*)\\{([a-z_][a-z0-9_]*)\\}\\s+ne\\s+([a-z_][a-z0-9_]*)\\s+then\\s+([a-z_][a-z0-9_]*)\\{([a-z_][a-z0-9_]*)\\}\\s*=\\s*([a-z_][a-z0-9_]*)',st[7])
  no<-capture('else\\s+([a-z_][a-z0-9_]*)\\{([a-z_][a-z0-9_]*)\\}\\s*=\\s*([a-z_][a-z0-9_]*)',st[8])
  capture('end',st[9]);capture('end',st[10])
  total<-capture('([a-z_][a-z0-9_]*)\\s*=\\s*sum\\(of\\s+([a-z_][a-z0-9_]*)\\{\\*\\}\\)',st[11])
  put<-capture('put\\s+("[^"]*")\\s+([a-z_][a-z0-9_]*)',st[12])
  same<-function(xs) length(unique(tolower(xs)))==1L
  if(!same(c(decl[1],yes[c(1,4)],no[1],total[2])) ||
     !same(c(outer[1],inner[c(2,4)])) || !same(c(inner[1],yes[c(2,5)],no[2])) ||
     !same(c(init1[1],yes[c(3,6)])) || !same(c(init2[1],no[3])) || !same(c(total[1],put[2]))) stop('bindings')
  n<-as.integer(decl[2]);opened<-as.integer(init1[2]);closed<-as.integer(init2[2])
  if(n!=100L || opened!=1L || closed!=0L || as.integer(outer[2])!=1L ||
     as.integer(outer[3])!=n || as.integer(inner[3])!=n) stop('pinned numeric profile')
  cells<-rep(NA_real_,n);pass<-1L;current<-NA_integer_;trips<-0L
  while(pass<=n) {
    current<-pass
    while(current<=n) {
      cells[current]<-if(is.na(cells[current]) || cells[current]!=opened) opened else closed
      current<-current+pass;trips<-trips+1L
    }
    pass<-pass+1L
  }
  amount<-sum(cells,na.rm=TRUE)
  cat('STATE:',pass,':',current,':',trips,':',paste(cells,collapse='|'),':',amount,'\n',sep='')
  # Native R integer rendering and literal decoding, independent of Python helpers.
  cat('RECORD:',hex(paste0(decode_literal(put[1]),sprintf('%.0f',amount),' ')),'\n',sep='')
} else if(args[1]=='original') {
  x<-NA_real_;y<-NA_real_;total<-NA_real_
  rows<-list();records<-character()
  for(i in 1:2) {
    if(i==1L) x<-i else y<-i
    missing<-function(v) if(is.na(v)) '.' else sprintf('%.0f',v)
    rows[[length(rows)+1L]]<-c(x=x,y=y,i=i,total=total)
    records<-c(records,paste0('i:',i,' x:',missing(x),' y:',missing(y),' '))
  }
  i<-3;total<-x+y;rows[[3]]<-c(x=x,y=y,i=i,total=total)
  records<-c(records,paste0('total:',total,' '))
  write.table(do.call(rbind,rows),row.names=FALSE,col.names=TRUE,quote=FALSE,sep=',',na='')
  for(record in records) cat('RECORD:',hex(record),'\n',sep='')
} else stop('unknown witness mode')
