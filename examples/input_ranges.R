# DS-059 independent bounded expansion, not Python-plan interpretation.
expand_names <- function(text) {
  if(any(as.integer(charToRaw(text))>127)) stop('ASCII source names')
  text<-tolower(trimws(text));terms<-character();names<-character()
  while(nzchar(text)) {
    m<-regmatches(text,regexec('^([a-z_][a-z0-9_]{0,31})(?:\\s*-\\s*([a-z_][a-z0-9_]{0,31}))?(?=\\s|$)',text,perl=TRUE))[[1]]
    if(!length(m)) stop('whole term')
    first<-m[2];last<-if(length(m)>2) m[3] else ''
    if(nzchar(last)) {
      a<-regmatches(first,regexec('^([a-z_][a-z0-9_]*?)([0-9]+)$',first,perl=TRUE))[[1]]
      b<-regmatches(last,regexec('^([a-z_][a-z0-9_]*?)([0-9]+)$',last,perl=TRUE))[[1]]
      if(!length(a)||!length(b)||a[2]!=b[2]||nchar(a[3])>2||nchar(b[3])>2||
         substr(a[3],1,1)=='0'||substr(b[3],1,1)=='0') stop('range spelling')
      low<-as.integer(a[3]);high<-as.integer(b[3])
      if(low<1||high>64||low>high||length(names)+high-low+1>32) stop('range bounds')
      names<-c(names,paste0(a[2],seq.int(low,high)));terms<-c(terms,paste0(first,'-',last))
    } else {names<-c(names,first);terms<-c(terms,first)}
    if(length(names)>32||length(terms)>32) stop('name bound')
    text<-trimws(substring(text,nchar(m[1])+1))
  }
  reserved<-c('_n_','_error_','_all_','_numeric_','_character_','_infile_','_file_','_ods_','_page_','_blankpage_')
  if(!length(names)||anyDuplicated(names)||any(names %in% reserved)) stop('unique ordinary names')
  list(names=names,terms=terms,range=any(grepl('-',terms,fixed=TRUE)))
}
if(sys.nframe()==0) {
  args<-commandArgs(trailingOnly=TRUE)
  cases<-readLines(args[1],warn=FALSE)
  for(text in cases) cat(tryCatch(paste0('OK:',paste(expand_names(text)$names,collapse=',')),error=function(e)'REFUSE'),'\n',sep='')
}
