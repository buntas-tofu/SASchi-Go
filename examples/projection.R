# Independent base-R projection and complete original-program witness.
# Repository/base-R evidence for maintainers; no live SAS.
args<-commandArgs(trailingOnly=TRUE)
hex<-function(x) paste(sprintf('%02x',as.integer(charToRaw(x))),collapse='')
ordinary<-function(x) grepl('^[a-z_][a-z0-9_]{0,31}$',x,perl=TRUE) &&
  !(x %in% c('_n_','_error_','_all_','_numeric_','_character_','_temporary_',
             '_infile_','_file_','_ods_','_page_','_blankpage_'))
expand<-function(text) {
  if(any(as.integer(charToRaw(text))>127)) stop('ASCII names')
  text<-tolower(trimws(gsub(' *- *','-',text)))
  tokens<-strsplit(text,' +',perl=TRUE)[[1]];answer<-character()
  for(token in tokens) {
    pair<-strsplit(token,'-',fixed=TRUE)[[1]]
    if(length(pair)==1 && ordinary(token)) answer<-c(answer,token) else {
      if(length(pair)!=2) stop('range')
      suffix<-sub('^.*?([0-9]+)$','\\1',pair,perl=TRUE)
      prefix<-sub('[0-9]+$','',pair)
      if(any(!grepl('^[1-9][0-9]*$',suffix)) || prefix[1]!=prefix[2] ||
         any(nchar(suffix)>2) || any(!vapply(pair,ordinary,FALSE))) stop('range')
      lo<-as.integer(suffix[1]);hi<-as.integer(suffix[2])
      if(lo>hi || lo<1 || hi>64) stop('range bounds')
      answer<-c(answer,paste0(prefix[1],seq.int(lo,hi)))
    }
  }
  if(!length(answer) || length(answer)>64 || anyDuplicated(answer) ||
     any(!vapply(answer,ordinary,FALSE))) stop('list')
  answer
}
select<-function(schema,mode,names) {
  if(is.null(mode)) return(schema)
  if(!(mode %in% c('keep','drop')) || any(!(names %in% schema))) stop('unresolved')
  selected<-schema[(schema %in% names)==(mode=='keep')]
  if(!length(selected)) stop('empty')
  selected
}
selection<-function(text,option=FALSE) {
  pattern<-if(option) '^(keep|drop) *= *(.*)$' else '^(keep|drop) +(.*)$'
  fields<-regmatches(tolower(trimws(text)),regexec(pattern,tolower(trimws(text)),perl=TRUE))[[1]]
  if(length(fields)!=3) stop('selection')
  list(mode=fields[2],names=expand(fields[3]))
}
choose<-function(schema,p) if(is.null(p)) schema else select(schema,p$mode,p$names)
dataset<-function(text,keyword) {
  fields<-regmatches(text,regexec(paste0('^',keyword,' +([a-z_][a-z0-9_]*)(?: *\\((.*)\\))?$'),
                                  text,perl=TRUE))[[1]]
  if(!length(fields)) stop('dataset')
  list(name=fields[2],projection=if(length(fields)>2 && nzchar(fields[3])) selection(fields[3],TRUE) else NULL)
}
encoded<-function(row) paste(vapply(row,function(v) {
  if(is.character(v)) paste0('C',hex(v)) else if(is.na(v)) 'M' else paste0('N',sprintf('%.17g',v))
},''),collapse=',')
program<-function(path) {
  code<-paste(readLines(path,warn=FALSE),collapse='\n')
  text<-strsplit(paste0(code,' '),';',fixed=TRUE)[[1]]
  if(nzchar(trimws(tail(text,1)))) stop('unterminated')
  text<-trimws(head(text,-1));tables<-list();logs<-character();at<-1L
  while(at<=length(text)) {
    header<-dataset(tolower(text[at]),'data');at<-at+1L;body<-character()
    while(at<=length(text) && tolower(text[at])!='run') {body<-c(body,text[at]);at<-at+1L}
    if(at>length(text)) stop('run');at<-at+1L
    schema<-list();input<-list(list());outp<-header$projection;explicit<-any(tolower(body)=='output')
    for(statement in body) {
      lower<-tolower(statement)
      if(grepl('^length ',lower)) {
        fields<-regmatches(lower,regexec('^length +([a-z_][a-z0-9_]*) +\\$([0-9]+)$',lower))[[1]]
        if(length(fields)!=3) stop('length')
        schema[[fields[2]]]<-paste0('character:',fields[3])
      } else if(grepl('^set ',lower)) {
        source<-dataset(lower,'set');table<-tables[[source$name]]
        if(is.null(table)) stop('missing source')
        names<-choose(names(table$schema),source$projection)
        for(n in names) if(is.null(schema[[n]])) schema[[n]]<-table$schema[[n]]
        input<-lapply(table$rows,function(row) row[names])
      } else if(grepl('^(keep|drop) ',lower)) {
        if(!is.null(outp)) stop('conflicting output')
        outp<-selection(lower)
      } else if(grepl('^[a-z_][a-z0-9_]* *=',lower)) {
        dest<-trimws(strsplit(lower,'=',fixed=TRUE)[[1]][1])
        if(is.null(schema[[dest]])) schema[[dest]]<-'number'
        rhs<-trimws(sub('^[^=]*=','',statement))
        if(!grepl("^'.*'$",rhs)) {
          refs<-regmatches(tolower(rhs),gregexpr('[a-z_][a-z0-9_]*',tolower(rhs),perl=TRUE))[[1]]
          for(n in refs) if(is.null(schema[[n]])) schema[[n]]<-'number'
        }
      } else if(!(lower=='output' || grepl('^put ',lower))) stop('unsupported original statement')
    }
    chosen<-choose(names(schema),outp);rows<-list()
    for(inrow in input) {
      row<-lapply(schema,function(spec) if(grepl('^character:',spec)) strrep(' ',as.integer(sub('.*:','',spec))) else NA_real_)
      for(n in names(inrow)) row[[n]]<-inrow[[n]]
      for(statement in body) {
        lower<-tolower(statement)
        if(lower=='output') rows[[length(rows)+1L]]<-row[chosen] else
        if(grepl('^put ',lower)) {
          names<-strsplit(trimws(sub('^put +','',lower)),' +',perl=TRUE)[[1]]
          if(any(!grepl('^[a-z_][a-z0-9_]*=$',names))) stop('put')
          names<-sub('=$','',names)
          logs<-c(logs,paste(vapply(names,function(n) paste0(n,'=',if(is.character(row[[n]]))
            sub(' +$','',row[[n]]) else if(is.na(row[[n]])) '.' else sprintf('%.17g',row[[n]])),''),collapse=' '))
        } else if(grepl('^[a-z_][a-z0-9_]* *=',lower)) {
          dest<-trimws(strsplit(lower,'=',fixed=TRUE)[[1]][1]);rhs<-trimws(sub('^[^=]*=','',statement))
          if(grepl("^'.*'$",rhs)) value<-substr(rhs,2,nchar(rhs)-1) else {
            parts<-trimws(strsplit(tolower(rhs),'+',fixed=TRUE)[[1]])
            values<-vapply(parts,function(p) if(p %in% names(row)) row[[p]] else as.numeric(p),0.0)
            value<-sum(values)
          }
          row[[dest]]<-value
        }
      }
      if(!explicit) rows[[length(rows)+1L]]<-row[chosen]
    }
    tables[[header$name]]<-list(schema=schema[chosen],rows=rows)
  }
  cat('STATEMENTS:',length(text),'\n',sep='')
  for(n in names(tables)) {
    table<-tables[[n]];cat('TABLE:',n,'\n',sep='')
    cat('SCHEMA:',paste(paste(names(table$schema),unlist(table$schema),sep='='),collapse=','),'\n',sep='')
    for(row in table$rows) cat('ROW:',encoded(row),'\n',sep='')
  }
  for(log in logs) cat('LOG:',hex(log),'\n',sep='')
}
if(args[1]=='program') program(args[2]) else if(args[1]=='cases') {
  cases<-read.csv(args[2],stringsAsFactors=FALSE,check.names=FALSE)
  for(i in seq_len(nrow(cases))) {
    answer<-tryCatch({schema<-strsplit(cases$schema[i],' ',fixed=TRUE)[[1]]
      p<-selection(paste(cases$mode[i],cases$list[i]));paste0('OK:',paste(choose(schema,p),collapse=','))},
      error=function(e) 'REFUSE')
    cat(answer,'\n',sep='')
  }
} else stop('mode')
