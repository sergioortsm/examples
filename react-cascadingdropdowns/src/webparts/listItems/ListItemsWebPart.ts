import * as React from 'react';
import * as ReactDom from 'react-dom';
import { Version } from '@microsoft/sp-core-library';
import {
  BaseClientSideWebPart,
  IPropertyPaneConfiguration,
  PropertyPaneTextField
} from '@microsoft/sp-webpart-base';

import * as strings from 'ListItemsWebPartStrings';
import ListItems from './components/ListItems';
import { IListItemsProps } from './components/IListItemsProps';

import { SPHttpClient, SPHttpClientResponse } from '@microsoft/sp-http';
import { escape } from '@microsoft/sp-lodash-subset';

export interface IListItemsWebPartProps {
  listName: string;
  description: string;
}

export default class ListItemsWebPart extends BaseClientSideWebPart<IListItemsWebPartProps> {

  public render(): void {
    const element: React.ReactElement<IListItemsProps> = React.createElement(ListItems, {
      listName: this.properties.listName,
      description :this.properties.description
    });
 
    ReactDom.render(element, this.domElement);
  }

  protected onDispose(): void {
    ReactDom.unmountComponentAtNode(this.domElement);
  }

  protected get dataVersion(): Version {
    return Version.parse('1.0');
  }

  private validateListName(value: string): Promise<string> {
    return new Promise<string>((resolve: (validationErrorMessage: string) => void, reject: (error: any) => void): void => {
      if (value === null ||
        value.length === 0) {
        resolve('Provide the list name');
        return;
      }
 
      this.context.spHttpClient.get(this.context.pageContext.web.absoluteUrl + `/_api/web/lists/getByTitle('${escape(value)}')?$select=Id`, SPHttpClient.configurations.v1)
        .then((response: SPHttpClientResponse): void => {
          if (response.ok) {
            resolve('');
            return;
          }
          else if (response.status === 404) {
            resolve(`List '${escape(value)}' doesn't exist in the current site`);
            return;
          }
          else {
            resolve(`Error: ${response.statusText}. Please try again`);
            return;
          }
        })
        .catch((error: any): void => {
          resolve(error);
        });
    });
  }

  private validateDescription(value: string): string {
    if (value === null ||
      value.trim().length === 0) {
      return 'Provide a description';
    }
 
    if (value.length > 10) {
      return 'Description should not be longer than 10 characters';
    }
 
    return '';
  }
  
  protected getPropertyPaneConfiguration(): IPropertyPaneConfiguration {
    return {
      pages: [
        {
          header: {
            description: strings.PropertyPaneDescription
          },
          groups: [
            {
              groupName: strings.BasicGroupName,
              groupFields: [
               PropertyPaneTextField('description', {
                 label: strings.DescriptionFieldLabel,
                 onGetErrorMessage: this.validateDescription.bind(this)
               }),
               PropertyPaneTextField('listName', {
                 label: strings.ListNameFieldLabel,
                 onGetErrorMessage: this.validateListName.bind(this),
                 deferredValidationTime: 500
               })              
              ]
            }
          ]
        }
      ]
    };
  }
}
