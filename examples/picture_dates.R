# Independent whole-source date-picture witness. No translator or Python helpers.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L,!file.exists(args[2]))
input_path <- args[1];output_path <- args[2]
script <- sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1])
source(file.path(dirname(normalizePath(script)),'format_oracle_common.R'))
invisible(Sys.setlocale('LC_TIME','C'))
epoch <- as.Date('1960-01-01')
read_date <- function(text) {
 if(text=='.') return(NULL)
 months <- c('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC')
 stopifnot(grepl('^[0-9]{2}[A-Za-z]{3}[0-9]{4}$',text))
 month <- match(toupper(substr(text,3,5)),months);stopifnot(!is.na(month))
 iso <- sprintf('%s-%02d-%s',substr(text,6,9),month,substr(text,1,2))
 d <- as.Date(iso);stopifnot(!is.na(d),format(d,'%Y-%m-%d')==iso)
 as.numeric(d-epoch)
}
quoted <- function(text) {stopifnot(startsWith(text,"'"),endsWith(text,"'"));gsub("''","'",substr(text,2,nchar(text)-1),fixed=TRUE)}
endpoint <- function(text) {
 if(tolower(text)=='low') return(as.numeric(as.Date('1753-01-01')-epoch))
 if(tolower(text)=='high') return(as.numeric(as.Date('3999-12-31')-epoch))
 read_date(substr(text,2,nchar(text)-2))
}
parse_picture <- function(text) {
 head <- regmatches(text,regexec('(?s)^picture[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+(.+)$',text,ignore.case=TRUE,perl=TRUE))[[1]]
 stopifnot(length(head)==3L)
 remain <- head[3];entries <- list();other <- NULL
 bound <- "(?:low|high|'[0-9]{2}[A-Za-z]{3}[0-9]{4}'[dD])"
 pattern <- paste0("^[[:space:]]*(other|(",bound,")[[:space:]]*-[[:space:]]*(<)?[[:space:]]*(",bound,"))[[:space:]]*=[[:space:]]*('(?:[^']|'')*')[[:space:]]*(\\([[:space:]]*datatype[[:space:]]*=[[:space:]]*date[[:space:]]*\\))?")
 while(nchar(trimws(remain))) {
  m <- regmatches(remain,regexec(pattern,remain,ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(m)==7L)
  render <- list(text=quoted(m[6]),dt=nzchar(m[7]))
  if(tolower(m[2])=='other') {stopifnot(is.null(other));other <- render} else {
   entries[[length(entries)+1L]] <- c(list(lower=endpoint(m[3]),upper=endpoint(m[5])-as.integer(nzchar(m[4]))),render)
  }
  remain <- substring(remain,nchar(m[1])+1L)
 }
 list(name=tolower(head[2]),entries=entries,other=other)
}
date_display <- function(value,definition) {
 selected <- definition$other
 if(!is.null(value)) for(item in definition$entries) if(value>=item$lower && value<=item$upper) {selected <- item;break}
 if(is.null(selected)) return(if(is.null(value)) 'ERROR' else '.')
 text <- selected$text
 if(selected$dt) {
  if(is.null(value)) return('ERROR')
  d <- epoch+value
  tokens <- gregexpr('%0d|%[dbBY%]',text,perl=TRUE)[[1]]
  if(tokens[1]!=-1L) {
   lens <- attr(tokens,'match.length');out <- '';start <- 1L
   for(j in seq_along(tokens)) {
    token <- substr(text,tokens[j],tokens[j]+lens[j]-1L)
    literal <- if(tokens[j]>start) substr(text,start,tokens[j]-1L) else ''
    replacement <- switch(token,'%0d'=format(d,'%d'),'%d'=as.character(as.integer(format(d,'%d'))),'%b'=format(d,'%b'),'%B'=format(d,'%B'),'%Y'=format(d,'%Y'),'%%'='%')
    out <- paste0(out,literal,replacement);start <- tokens[j]+lens[j]
   }
   text <- paste0(out,substring(text,start))
  }
 }
 sub(' +$','',text)
}
tables <- list();formats <- list();reports <- list();title <- NULL;trace <- list()
add <- function(x) trace[[length(trace)+1L]] <<- x
texts <- vapply(statements,function(s) s$text,'');norm <- tolower(gsub('[[:space:]]+',' ',texts))
payloads <- Filter(function(e)e$kind=='opaque_data',events);pi <- 1L;i <- 1L;steps <- 0L;input_count <- 0L;title_count <- 0L
while(i<=length(texts)) {
 if(norm[i]=='proc format') {
  stopifnot(norm[i+2L]=='run');definition <- parse_picture(texts[i+1L]);formats[[definition$name]] <- definition
  add(paste('date_picture',definition$name,length(definition$entries),as.integer(!is.null(definition$other)),sep='|'));i <- i+3L
 } else if(startsWith(norm[i],'data ')) {
  name <- tolower(sub('^data[[:space:]]+','',texts[i],ignore.case=TRUE))
  stopifnot(norm[i+1L]=='infile cards',norm[i+3L]=='cards',norm[i+4L]=='run')
  remain <- sub('^input[[:space:]]+','',texts[i+2L],ignore.case=TRUE);schema <- list();reads <- list()
  while(nchar(trimws(remain))) {
   m <- regmatches(remain,regexec('^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)(?:[[:space:]]*:[[:space:]]*(?:\\$([0-9]+)\\.|(date9)\\.))?(?=[[:space:]]|$)',remain,ignore.case=TRUE,perl=TRUE))[[1]]
   stopifnot(length(m)==4L);col <- tolower(m[2]);kind <- if(nzchar(m[3])) 'character' else if(nzchar(m[4])) 'date' else 'number';width <- if(kind=='character') as.integer(m[3]) else 8L
   schema[[col]] <- list(type=if(kind=='character') 'character' else 'number',length=width);reads[[col]] <- kind;remain <- substring(remain,nchar(m[1])+1L)
  }
  payload <- payloads[[pi]];pi <- pi+1L;rows <- list()
  for(j in seq_along(payload$records)) {
   tokens <- strsplit(trimws(payload$records[j]),'[[:space:]]+')[[1]];stopifnot(length(tokens)==length(reads));row <- list()
   for(k in seq_along(reads)) {
    col <- names(reads)[k];kind <- reads[[k]];token <- tokens[k]
    value <- if(kind=='character') paste0(token,strrep(' ',schema[[col]]$length-nchar(token))) else if(kind=='date') read_date(token) else if(token=='.') NULL else as.numeric(token)
    row[col] <- list(value)
   }
   rows[[j]] <- row;add(paste('picture_input',name,j,1,sep='|'));add(paste('picture_output',name,j,sep='|'))
  }
  add(paste('picture_input',name,length(rows)+1L,0,sep='|'));input_count <- input_count+as.integer(length(rows))
  tables[[name]] <- list(schema=schema,rows=rows);i <- i+5L
 } else if(startsWith(norm[i],'proc print ')) {
  m <- regmatches(texts[i],regexec('^proc[[:space:]]+print[[:space:]]+data[[:space:]]*=[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)(?:[[:space:]]*\\([[:space:]]*obs[[:space:]]*=[[:space:]]*([0-9]+)[[:space:]]*\\))?$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]]
  stopifnot(length(m)==3L);name <- tolower(m[2]);limit <- if(nzchar(m[3])) as.integer(m[3]) else length(tables[[name]]$rows);i <- i+1L
  columns <- strsplit(tolower(sub('^var[[:space:]]+','',texts[i],ignore.case=TRUE)),'[[:space:]]+')[[1]];i <- i+1L
  b <- regmatches(texts[i],regexec('^format[[:space:]]+(.+)[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)\\.$',texts[i],ignore.case=TRUE,perl=TRUE))[[1]];stopifnot(length(b)==3L)
  bindings <- strsplit(tolower(b[2]),'[[:space:]]+')[[1]];fmt <- tolower(b[3]);i <- i+1L
  if(startsWith(norm[i],'title ')) {title <- quoted(sub('^title[[:space:]]+','',texts[i],ignore.case=TRUE));title_count <- title_count+1L;add(paste0('picture_title|set|',hex(title)));i <- i+1L}
  stopifnot(norm[i]=='run');i <- i+1L
  rows <- head(tables[[name]]$rows,limit);ordinal <- length(reports)+1L
  lines <- c(if(is.null(title)) character() else paste0('TITLE: ',title),paste0('obs ',paste(columns,collapse=' ')))
  add(paste0('picture_print|',name,'|',ordinal,'|',length(rows),'|',paste(columns,collapse=',')))
  for(j in seq_along(rows)) {
   row <- rows[[j]];cells <- vapply(columns,function(col) {
    value <- row[[col]]
    if(col %in% bindings) json_string(date_display(value,formats[[fmt]])) else if(tables[[name]]$schema[[col]]$type=='character') json_string(sub(' +$','',value)) else if(is.null(value)) '.' else integer_text(value)
   },'')
   line <- paste(j,paste(cells,collapse=' '));lines <- c(lines,line);add(paste0('picture_row|',ordinal,'|',j,'|',hex(line)))
  }
  key <- sprintf('print_%02d.txt',ordinal);reports[[key]] <- paste0(paste(lines,collapse='\n'),'\n');add(paste0('picture_artifact|',key,'|',nchar(reports[[key]],type='bytes')))
 } else if(norm[i]=='title' || startsWith(norm[i],'title ')) {
  title <- if(norm[i]=='title') NULL else quoted(sub('^title[[:space:]]+','',texts[i],ignore.case=TRUE));title_count <- title_count+1L
  add(if(is.null(title)) 'picture_title|reset' else paste0('picture_title|set|',hex(title)));i <- i+1L
 } else stop('unconsumed whole R statement')
 steps <- steps+1L
}
result <- list(datasets=tables,log=list());if(length(reports)) result$reports <- reports
accounting <- list(language_statements=as.integer(length(statements)),opaque_payloads=as.integer(length(payloads)),steps=steps,input_records=input_count,
 input_attempts=input_count+as.integer(length(tables)),title_sets=title_count,prints=as.integer(length(reports)),statement_lines=as.list(vapply(statements,function(s)s$line,1L)))
dir.create(output_path,recursive=TRUE)
write_json('result.json',result);write_json('accounting.json',accounting);write_json('trace.json',trace)
