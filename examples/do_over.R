# DS-040 independent native-R alias and iteration witness. No live SAS.
args <- commandArgs(trailingOnly=TRUE)
if(args[1]=='cases') {
  cases <- read.csv(args[2], stringsAsFactors=FALSE, na.strings=NULL)
  for(j in seq_len(nrow(cases))) {
    c <- cases[j,]
    xs <- as.numeric(strsplit(c$values,'|',fixed=TRUE)[[1]])
    names(xs) <- paste0('x',seq_along(xs))
    order <- as.integer(strsplit(c$order,'|',fixed=TRUE)[[1]])
    if(length(xs)<1 || length(xs)>1024 || length(order)!=length(xs)) stop('profile')
    trip <- 0L
    for(name in names(xs)[order]) {
      before <- xs[[name]]
      xs[[name]] <- before+c$delta
      xs[['x1']] <- xs[['x1']]+1
      after <- xs[[name]]
      trip <- trip+1L
      vals <- c(unname(xs),c$delta,before,after,NA_real_)
      cat(c$id,':',trip,':',paste(ifelse(is.na(vals),'M',sprintf('%.17g',vals)),collapse='|'),'\n',sep='')
    }
  }
} else if(args[1]=='sizes') {
  for(n in as.numeric(strsplit(args[2],',',fixed=TRUE)[[1]])) {
    if(!is.finite(n) || n!=trunc(n) || n<1 || n>1024) cat('REFUSE\n') else
      cat(paste(seq_len(n)-1L,collapse='|'),'\n',sep='')
  }
} else if(args[1]=='program') {
  source <- paste(readLines(args[2],warn=FALSE),collapse='\n')
  source <- gsub('(?s)/\\*.*?\\*/','',source,perl=TRUE)
  st <- tolower(trimws(strsplit(source,';',fixed=TRUE)[[1]])); st <- st[nzchar(st)]
  # Consume every statement of the pinned file. No ignored program tail.
  if(length(st)!=10L || st[1]!='data _null_' || st[7]!='end' || st[10]!='run') stop('whole-program profile')
  capture <- function(pattern,text) {
    p <- regmatches(text,regexec(pattern,text,perl=TRUE))[[1]]
    if(!length(p)) stop('unhandled program statement')
    p[-1]
  }
  decl <- capture('^array ([a-z_][a-z0-9_]*) ([a-z_]+)([0-9]+)-([a-z_]+)([0-9]+)$',st[2])
  init <- capture('^([a-z_][a-z0-9_]*)=([0-9]+)$',st[3])
  loop <- capture('^do over ([a-z_][a-z0-9_]*)$',st[4])
  write <- capture('^([a-z_][a-z0-9_]*)=([a-z_][a-z0-9_]*)$',st[5])
  inc <- capture('^([a-z_][a-z0-9_]*)=([a-z_][a-z0-9_]*)\\+([0-9]+)$',st[6])
  agg <- capture('^([a-z_][a-z0-9_]*)=sum\\(of ([a-z_][a-z0-9_]*)\\{\\*\\}\\)$',st[8])
  put <- capture('^put ([a-z_][a-z0-9_]*)$',st[9])
  if(loop!=decl[1] || write[1]!=loop || write[2]!=init[1] ||
     any(inc[1:2]!=init[1]) || agg[2]!=loop || put!=agg[1] || decl[2]!=decl[4]) stop('variable identity')
  lo<-as.integer(decl[3]); hi<-as.integer(decl[5]); n<-as.numeric(init[2]); by<-as.numeric(inc[3])
  if(lo!=1L || hi!=10L || n!=1 || by!=1) stop('pinned numeric profile')
  cells <- setNames(rep(NA_real_,hi-lo+1L),paste0(decl[2],lo:hi))
  for(name in names(cells)) { cells[[name]]<-n; n<-n+by }
  total <- sum(cells,na.rm=TRUE)
  cat('STATE:',n,':',paste(cells,collapse='|'),':',total,'\n',sep='')
  record <- paste0(sprintf('%.0f',total),' ')
  cat('RECORD:',paste(sprintf('%02x',as.integer(charToRaw(record))),collapse=''),'\n',sep='')
} else stop('unknown DO OVER witness mode')
